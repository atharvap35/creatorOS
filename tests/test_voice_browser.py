"""Browser tests for the voice dock's recognition lifecycle.

These run under Playwright and are skipped when it is not installed, because the
normal `pytest tests/` run is deliberately kept free of a browser dependency.

The bug guarded here is worth a test of its own. The recognition session used to
be reopened from a timer whenever Chrome reported `no-speech`. Chrome had not
released the microphone yet, so each restart threw, the catch retried again, and
the session was torn down and rebuilt in a loop. The microphone light stayed on
and no audio ever arrived - indistinguishable from a broken microphone, even
though the microphone worked perfectly in every other application.

The invariant: one press of the mic button creates exactly one recognition
session, and that session is never restarted.
"""
import re
import time

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed"
)

BASE_URL = "http://127.0.0.1:8078"

# A stub that records every Recognition instance ever constructed, so a restart
# storm shows up as a growing count rather than as a vague "it didn't work".
STUB = r"""
window.__spoken = [];
window.__sessions = [];
window.__starts = 0;

class FakeRecognition {
  constructor() {
    this.lang = "en-US";
    this.interimResults = true;
    this.continuous = false;
    this.maxAlternatives = 1;
    this.__stopped = 0;
    window.__sessions.push(this);
    window.__rec = this;
  }
  start() { window.__starts += 1; if (this.onstart) this.onstart(); }
  stop()  { this.__stopped += 1; if (this.onend) this.onend(); }
  abort() { this.__aborted = (this.__aborted || 0) + 1; }
  __emit(text, isFinal) {
    const results = [{ 0: { transcript: text, confidence: 0.95 }, isFinal }];
    results.length = 1;
    if (this.onresult) this.onresult({ resultIndex: 0, results });
  }
  __say(t) { this.__emit(t, true); }
  __interim(t) { this.__emit(t, false); }
}

window.SpeechRecognition = FakeRecognition;
window.webkitSpeechRecognition = FakeRecognition;

// Chromium exposes these as read-only, so they must be redefined, not assigned.
Object.defineProperty(window, "speechSynthesis", {
  configurable: true,
  value: {
    speak(u) {
      window.__spoken.push(u.text);
      setTimeout(() => u.onstart && u.onstart(), 0);
      setTimeout(() => u.onend && u.onend(), 5);
    },
    cancel() {},
    getVoices: () => [],
  },
});
Object.defineProperty(window, "SpeechSynthesisUtterance", {
  configurable: true,
  value: function (t) { this.text = t; this.rate = 1; this.pitch = 1; },
});
"""


def _sign_up(page):
    page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded")
    page.fill('input[name="name"]', "Voice Tester")
    page.fill(
        'input[name="email"]',
        f"voice-{int(time.time() * 1000) % 10 ** 9}@example.com",
    )
    page.fill('input[name="password"]', "supersecret")
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.click('form button[type="submit"]')
    page.goto(f"{BASE_URL}/today", wait_until="domcontentloaded")
    page.wait_for_selector("[data-voice-toggle]")


def _speak(page, phrase):
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("t => window.__rec.__say(t)", phrase)


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    p = ctx.new_page()
    p.set_default_timeout(30000)
    p.add_init_script(STUB)
    errors = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    _sign_up(p)
    p._voice_errors = errors
    yield p
    assert not p._voice_errors, f"unhandled JS errors: {p._voice_errors}"
    ctx.close()


def test_one_press_creates_exactly_one_recognition_session(page):
    """The regression: a single press must never open a second session."""
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__sessions.length") == 1
    assert page.evaluate("() => window.__starts") == 1

    page.evaluate("() => window.__rec.__say('what should i do')")
    page.wait_for_timeout(2600)

    # Speech arrived and was submitted. Still exactly one session - no restart.
    assert page.evaluate("() => window.__sessions.length") == 1
    assert page.evaluate("() => window.__starts") == 1


def test_speech_releases_the_microphone(page):
    # Deliberately not a navigation command: navigating would discard the
    # stubbed state this assertion depends on.
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("() => window.__rec.__say('what should i do')")
    page.wait_for_timeout(1500)
    assert page.evaluate("() => window.__rec.__stopped") >= 1


def test_question_is_answered_and_spoken(page):
    _speak(page, "what should i do today")
    page.wait_for_selector("[data-voice-answer] p", state="visible", timeout=15000)
    answer = page.inner_text("[data-voice-answer]")
    # Grounding is explicit: the verdict must be shown, not implied.
    assert "grounded" in answer or "not enough" in answer
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__spoken.length > 0")


def test_navigation_command_routes(page):
    _speak(page, "go to money")
    page.wait_for_url(lambda u: "/money" in u, timeout=15000)


def test_no_speech_gives_a_helpful_message_and_does_not_loop(page):
    """The old code retried four times, which is what masked the restart storm."""
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("() => { window.__rec.onerror({ error: 'no-speech' });"
                  " window.__rec.onend(); }")
    page.wait_for_timeout(800)

    message = page.inner_text("[data-voice-body]")
    assert "microphone" in message.lower()
    # The typing fallback must be offered, so the feature degrades.
    assert page.evaluate('() => !document.querySelector("[data-voice-typebox]").hidden')
    # And critically: no additional sessions were created.
    assert page.evaluate("() => window.__sessions.length") == 1


def test_interim_speech_is_shown_live(page):
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("() => window.__rec.__interim('go to')")
    page.wait_for_timeout(250)
    assert "go to" in page.inner_text("[data-voice-body]")

# ---------------------------------------------------------------------------
# whole-desk verbs: speech wired to the product's own actions

@pytest.mark.parametrize("phrase", ["clear my day", "clear the day", "triage my day"])
def test_clear_my_day_runs_the_real_triage_action(page, phrase):
    """"clear my day" used to be routed to the Copilot as a question, even though
    a deterministic triage action already existed."""
    _speak(page, phrase)
    # runAction reports into the voice panel, not the Copilot answer card.
    page.wait_for_function(
        "() => /\\d+ must do/.test(document.querySelector('[data-voice-body]').textContent)",
        timeout=15000,
    )
    said = page.inner_text("[data-voice-body]")

    # The service's own wording, not something composed in the browser.
    assert re.search(r"\d+ must do", said), said
    assert "Must do:" in said
    # Reasons are joined with one full stop, never two.
    assert ".." not in said
    # It is read-only, so it must not interrupt with a confirmation prompt.
    assert page.evaluate('() => document.querySelector("[data-voice-confirm-no]").hidden')


@pytest.mark.parametrize("phrase", ["rebalance my week", "rebalance the week"])
def test_rebalance_runs_the_real_action(page, phrase):
    _speak(page, phrase)
    page.wait_for_function(
        "() => document.querySelector('[data-voice-body]').textContent.trim().length > 0",
        timeout=15000,
    )
    said = page.inner_text("[data-voice-body]")
    # Either the grounded "within capacity" answer or a real overload notice -
    # both are the service's words, and neither may be a refusal.
    assert said.strip()
    assert "don't recognise" not in said.lower()


def test_plan_my_week_is_confirmed_before_it_writes(page):
    """propose_week writes a plan record, so it must ask first."""
    page.goto(f"{BASE_URL}/today", wait_until="domcontentloaded")
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("() => window.__rec.__say('plan my week')")
    page.wait_for_selector("[data-voice-confirm-no]", state="visible", timeout=15000)

    prompt = page.inner_text("[data-voice-body]").lower()
    assert "yes" in prompt and "cancel" in prompt
    assert page.evaluate("() => window.__sessions.length") == 1


@pytest.mark.parametrize(
    "phrase", ["clear my day", "rebalance my week", "plan my week"]
)
def test_action_commands_use_one_session(page, phrase):
    """The single-session invariant must hold for the action verbs too."""
    page.goto(f"{BASE_URL}/today", wait_until="domcontentloaded")
    page.click("[data-voice-toggle]")
    page.wait_for_timeout(250)
    page.evaluate("t => window.__rec.__say(t)", phrase)
    page.wait_for_timeout(2600)
    assert page.evaluate("() => window.__sessions.length") == 1
    assert page.evaluate("() => window.__starts") == 1
