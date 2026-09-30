/* Voice layer for Creator OS.
 *
 * Two capabilities, no API key and no new dependency:
 *   1. Voice operations — speak a command, it runs the same operation the
 *      button would, through the same endpoints the page uses.
 *   2. Voice responses — answers are read back with speechSynthesis.
 *
 * Design rules this file keeps, matching the rest of the product:
 *   - Deterministic routing. A spoken phrase maps to a known command by exact
 *     pattern. Nothing is inferred, and nothing is invented.
 *   - Same authority as the UI. Every request carries the normal session
 *     cookie and hits the same server endpoints, so `user_id` scoping and
 *     the existing auth checks apply unchanged.
 *   - Never silently mutate. A command that changes a record must be spoken
 *     back and confirmed out loud before it is sent.
 *   - Grounding is preserved. Spoken answers come from the copilot service,
 *     which refuses what it cannot know; voice only reads the result aloud.
 */

const Voice = (() => {
    "use strict";

    // ---- capability detection ---------------------------------------------
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const synth = window.speechSynthesis || null;
    const hasSpeechInput = Boolean(Recognition);
    const hasSpeechOutput = Boolean(synth);

    // ---- state ------------------------------------------------------------
    const state = {
        recognition: null,
        listening: false,
        speaking: false,
        speakReplies: true,
        // an action awaiting spoken/clicked confirmation
        pending: null,
        utterance: null,
        // guard-rail timers for the current recognition session
        silenceTimer: null,
        giveUpTimer: null,
    };

    // ---- spoken text formatting -------------------------------------------
    // Markdown bullets and emphasis read terribly aloud, so they are stripped
    // before anything reaches speechSynthesis.
    function toSpeech(text) {
        return String(text || "")
            .replace(/\*\*/g, "")
            .replace(/^#{1,6}\s*/gm, "")
            .replace(/^[-*+]\s+/gm, "")
            .replace(/`([^`]+)`/g, "$1")
            .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
            .replace(/\s*—\s*/g, ", ")
            .replace(/\s*–\s*/g, ", ")
            .replace(/\n{2,}/g, ". ")
            .replace(/\n/g, ". ")
            .replace(/\s{2,}/g, " ")
            .trim();
    }

    // Digits and symbols that a screen reader would spell out character by
    // character, so "8000" is written as "8000" but "$" and "%" get words.
    function normaliseForSpeech(text) {
        return toSpeech(text)
            .replace(/\$/g, " dollars ")
            .replace(/€/g, " euros ")
            .replace(/£/g, " pounds ")
            .replace(/₹/g, " rupees ")
            .replace(/%/g, " percent ")
            .replace(/\s{2,}/g, " ")
            .trim();
    }

    // ---- speech output -----------------------------------------------------
    function speak(text, { force = false } = {}) {
        if (!synth || (!state.speakReplies && !force)) return;
        const clean = normaliseForSpeech(text);
        if (!clean) return;
        synth.cancel();
        const u = new SpeechSynthesisUtterance(clean);
        u.rate = 1.03;
        u.pitch = 1.0;
        u.onstart = () => { state.speaking = true; sync(); };
        u.onend = () => { state.speaking = false; state.utterance = null; sync(); };
        u.onerror = () => { state.speaking = false; state.utterance = null; sync(); };
        state.utterance = u;
        synth.speak(u);
    }

    function stopSpeaking() {
        if (!synth) return;
        synth.cancel();
        state.speaking = false;
        state.utterance = null;
        sync();
    }

    // ---- command grammar ---------------------------------------------------
    // Ordered: the first match wins, so specific patterns come before the
    // generic catch-alls at the bottom.
    const COMMANDS = [
        // ---- capture: creates a record, confirmed before it is sent
        {
            id: "capture",
            mutating: true,
            patterns: [
                /^(?:new|add)\s+(idea|task|note)\s+(?:called\s+|titled\s+|named\s+)?(.+)$/i,
                /^(?:capture|note down|make a note|remind me to)\s+(?:an?\s+)?(.+)$/i,
            ],
            build(m) {
                // "new task called X" -> type from group 1, title from group 2.
                // "capture an idea about X" -> type defaults to idea, and the
                // leading noun is stripped so the title is just "X".
                const explicit = /^(?:new|add)\s+/i.test(m[0]);
                const type = explicit ? String(m[1]).toLowerCase() : "idea";
                let title = explicit ? m[2] : m[1];
                title = title.trim().replace(/^(?:idea|task|note|content|deal)\s+(?:about|on|for|that|to)\s+/i, "");
                if (!title) return null;
                return {
                    speak: `Capture ${type}: ${title}. Say yes to save it, or no to cancel.`,
                    run: () => postForm("/quick", { type, title }),
                };
            },
        },

        // ---- search: read-only
        {
            id: "search",
            patterns: [/^(?:search|look up|find|look for)\s+(?:for\s+)?(.+)$/i],
            build(m) {
                const q = m[1].trim();
                return {
                    speak: `Searching for ${q}.`,
                    run: () => { window.location.href = `/search?q=${encodeURIComponent(q)}`; },
                };
            },
        },

        // ---- whole-desk verbs: the product's own deterministic actions.
        // These are the verbs that need no entity id, which is what makes them
        // suited to speech: every other action needs the creator to point at a
        // specific deal, payment or episode, and a sentence cannot do that
        // reliably. Anything that would change a record is still confirmed first.
        {
            id: "triage",
            // Read-only — clear_slate groups today's work and writes nothing, so
            // it runs immediately rather than interrupting with a prompt.
            patterns: [
                /^(?:clear|triage|sort out)\s+(?:my\s+|the\s+)?day\b.*/i,
            ],
            build() {
                return {
                    speak: "Let me sort out your day.",
                    run: () => runAction("clear_slate"),
                };
            },
        },
        {
            id: "rebalance",
            // Read-only — rebalance_week proposes what to move and reschedules
            // nothing on its own.
            patterns: [
                /^rebalance\s+(?:my\s+|the\s+)?week\b.*/i,
            ],
            build() {
                return {
                    speak: "Checking how your week is loaded.",
                    run: () => runAction("rebalance_week"),
                };
            },
        },
        {
            id: "planweek",
            // Writes a plan record, so it is confirmed before it runs.
            mutating: true,
            patterns: [
                /^(?:plan|propose|lay out)\s+(?:my\s+|the\s+)?week\b.*/i,
            ],
            build() {
                return {
                    speak: "I will build a week plan from your deadlines and working days. "
                        + "Say yes to build it, or no to cancel.",
                    run: () => runAction("plan_week"),
                };
            },
        },

        // ---- copilot questions: grounded, answered by the existing service
        {
            id: "ask",
            patterns: [
                /^(?:what|which) should i (?:do|work on|focus on)\b.*/i,
                /^what am i forgetting\b.*/i,
                /^what(?:'s| is) (?:my )?money (?:waiting|owed|outstanding)\b.*/i,
                /^(?:how much )?money (?:am i )?waiting (?:on|for)\b.*/i,
                /^(?:what|which) deal[s]? needs? attention\b.*/i,
                /^(?:what|which) (?:idea|ideas) should i (?:do|prioriti[sz]e|make)\b.*/i,
                /^(?:what|how) (?:happened|changed) (?:this|my) (?:week|month)\b.*/i,
                /^(?:am i|how am i) (?:on track|doing)\b.*/i,
                /^(?:how|why) (?:is|am) (?:my )?(?:workload|week|capacity|overloaded)\b.*/i,
                /^(?:what|which) (?:can|should) i repurpose\b.*/i,
                /^(?:what|show me) (?:is )?(?:my )?biggest opportunity\b.*/i,
                /^(?:prepare|plan) (?:me )?for tomorrow\b.*/i,
                /^(?:what|which) brand relationship\b.*/i,
                /^(?:what should i post|what to post)\b.*/i,
            ],
            build(m) {
                const question = m[0].trim();
                return {
                    speak: "Let me check your records.",
                    run: () => askCopilot(question),
                };
            },
        },

        // ---- navigation
        {
            id: "navigate",
            patterns: [
                /^(?:go to|open|show me|take me to|navigate to)\s+(?:my |the )?(.+?)(?:\s+page)?$/i,
            ],
            build(m) {
                const target = m[1].trim().toLowerCase();
                const routes = [
                    [/\b(today|dashboard|home|start)\b/, "/today", "Today"],
                    [/\b(attention|alerts?|slipping)\b/, "/attention", "the Attention Center"],
                    [/\b(copilot|assistant|ask)\b/, "/copilot", "the Copilot"],
                    [/\b(timeline|history|activity)\b/, "/timeline", "the Timeline"],
                    [/\b(workflow|tasks?|plan my week)\b/, "/workflow", "your Workflow"],
                    [/\b(content|pipeline)\b/, "/content", "your Content"],
                    [/\b(ideas?|backlog)\b/, "/ideas", "your Ideas"],
                    [/\b(deals?)\b/, "/deals", "your Deals"],
                    [/\b(brands?)\b/, "/brands", "your Brands"],
                    [/\b(offers?)\b/, "/offers", "your Offers"],
                    [/\b(series?)\b/, "/series", "your Series"],
                    [/\b(money|revenue|invoices?|payments?)\b/, "/money", "Money"],
                    [/\b(rate card|rates|pricing)\b/, "/rate-card", "your Rate card"],
                    [/\b(growth|opportunit)/, "/growth/opportunities", "your Opportunities"],
                    [/\b(goals?)\b/, "/goals", "your Goals"],
                    [/\b(reviews?|weekly review)\b/, "/reviews/weekly", "your Weekly review"],
                    [/\b(business review|ceo)\b/, "/reviews/business", "the Business review"],
                    [/\b(calendar)\b/, "/calendar", "the Calendar"],
                    [/\b(library|assets)\b/, "/library", "the Library"],
                    [/\b(settings|profile)\b/, "/settings", "Settings"],
                    [/\b(quick|capture)\b/, "/quick", "Quick capture"],
                ];
                const hit = routes.find(([re]) => re.test(target));
                if (!hit) return null;
                const [, url, label] = hit;
                return {
                    // Deliberately silent: navigating unloads the page, which
                    // would cut the utterance off mid-word. The destination
                    // screen is its own confirmation.
                    speak: "",
                    label,
                    navigate: true,
                    run: () => { window.location.href = url; },
                };
            },
        },

        // ---- read the page aloud
        {
            id: "read",
            patterns: [
                /^read (?:this|the) page\b.*/i,
                /^read (?:it )?aloud\b.*/i,
                /^what(?:'s| is) on (?:this|the) page\b.*/i,
            ],
            build() {
                return { speak: "", run: () => readPage() };
            },
        },

        // ---- stop speaking
        {
            id: "stop",
            patterns: [/^(?:stop|quiet|silence|shush|enough)\b.*/i],
            build() {
                return { speak: "", run: () => stopSpeaking() };
            },
        },

        // ---- toggle spoken replies
        {
            id: "toggleSpeech",
            patterns: [
                /^(?:stop|turn off|disable) (?:speaking|talking|reading)\b.*/i,
                /^(?:start|turn on|enable) (?:speaking|talking|reading)\b.*/i,
            ],
            build(m) {
                const on = /^(?:start|turn on|enable)/i.test(m[0]);
                return {
                    speak: "",
                    run: () => {
                        state.speakReplies = on;
                        sync();
                        toast(on ? "Spoken replies on" : "Spoken replies off");
                        if (on) speak("Spoken replies on.", { force: true });
                    },
                };
            },
        },

        // ---- confirmation replies (only meaningful with something pending)
        {
            id: "confirm",
            patterns: [/^(?:yes|yeah|yep|confirm|do it|go ahead|sure|ok|okay|please do)\b/i],
            build() {
                if (!state.pending) return null;
                return { speak: "", run: () => confirmPending() };
            },
        },
        {
            id: "cancel",
            patterns: [/^(?:no|nope|cancel|stop that|don't|do not)\b/i],
            build() {
                if (!state.pending) return null;
                return { speak: "", run: () => cancelPending() };
            },
        },
    ];

    // Match in order and return the first command that produces a plan.
    function route(transcript) {
        const text = (transcript || "").trim();
        if (!text) return null;
        for (const command of COMMANDS) {
            for (const pattern of command.patterns) {
                const match = text.match(pattern);
                if (!match) continue;
                const plan = command.build(match);
                if (plan) return { ...plan, id: command.id, transcript: text, mutating: command.mutating };
            }
        }
        return null;
    }

    // ---- network helpers ---------------------------------------------------
    // The browser posts form-encoded bodies and follows the redirect itself,
    // so a voice capture lands on exactly the page a manual capture would.
    function postForm(url, fields) {
        const body = new URLSearchParams();
        Object.entries(fields).forEach(([k, v]) => body.append(k, v == null ? "" : v));
        return fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
            credentials: "same-origin",
        });
    }

    async function askCopilot(question) {
        const body = new URLSearchParams();
        body.append("question", question);
        let payload;
        try {
            const response = await fetch("/api/copilot/ask", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body,
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            payload = await response.json();
        } catch (err) {
            speak("I could not reach the Copilot just now. Your records were not changed.");
            toast("Could not reach the Copilot");
            return;
        }

        panel("answer", payload.answer);
        // The grounded/unanswerable verdict is spoken too, so a refusal is
        // never mistaken for a real answer.
        const verdict = payload.grounded
            ? ""
            : " I do not have that information in your records.";
        const citations = (payload.citations || []).length
            ? ` Based on ${payload.citations.length} of your records.`
            : "";
        speak(`${payload.answer}${verdict}${citations}`, { force: true });
        showAnswerPanel(payload);
    }

    // Runs one of the product's real actions and reports what actually happened.
    //
    // This posts to /api/actions/run, which dispatches the same slug the
    // on-screen button uses, so a spoken command can never do more than the UI
    // allows, and the service decides the outcome rather than the browser. The
    // numbers spoken back come from the same deterministic code that fills the
    // page, never from anything invented here.
    async function runAction(slug) {
        const body = new URLSearchParams();
        body.append("slug", slug);

        let payload;
        try {
            const response = await fetch("/api/actions/run", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body,
                credentials: "same-origin",
            });
            payload = await response.json();
        } catch (err) {
            speak("I could not run that just now. Nothing was changed.");
            toast("Could not run that action");
            return;
        }

        if (!payload || !payload.ok) {
            const message = (payload && payload.message) || "That did not go through.";
            panel("error", message);
            speak(message);
            return;
        }

        // A triage result says more out loud than its one-line summary, so the
        // must-do items are read back with the reason each one matters.
        const must = (payload.buckets && payload.buckets.must) || [];
        if (must.length) {
            // Reasons already end in a full stop, so they are trimmed before the
            // item's own separator is added — otherwise every item gets "..".
            const items = must.slice(0, 4).map((row) => {
                const reason = (row.reason || "").trim().replace(/\.\s*$/, "").toLowerCase();
                return `${row.title}${reason ? `, ${reason}` : ""}`;
            });
            const more = must.length > items.length
                ? ` And ${must.length - items.length} more.` : "";
            const said = `${payload.message} Must do: ${items.join(". ")}.${more}`;
            panel("answer", said);
            speak(said, { force: true });
        } else {
            panel("answer", payload.message);
            speak(payload.message, { force: true });
        }
    }

    // ---- page reading ------------------------------------------------------
    // Reads the meaningful part of whatever page is open, rather than the
    // whole DOM including navigation and chrome.
    //
    // The text is collected from the LIVE node, because innerText on a
    // detached clone has no layout and silently degrades to textContent —
    // which would drag in the hidden command palette and off-screen menus.
    const READ_SKIP = "nav, footer, script, style, form, .fab, .sidebar, .topbar, " +
        ".palette-backdrop, [data-voice-ui], [hidden], dialog";

    function visibleText(root) {
        const skip = [...root.querySelectorAll(READ_SKIP)];
        // Hide, read, restore. Cheaper and more accurate than walking the tree.
        skip.forEach((el) => { el.dataset.voiceWasHidden = el.hidden ? "1" : ""; el.hidden = true; });
        let text = "";
        try {
            text = root.innerText || "";
        } finally {
            skip.forEach((el) => { el.hidden = el.dataset.voiceWasHidden === "1"; });
            skip.forEach((el) => delete el.dataset.voiceWasHidden);
        }
        return text.replace(/\s{2,}/g, " ").trim();
    }

    function readPage() {
        const main = document.querySelector(".page-content")
            || document.querySelector("main")
            || document.body;
        const text = visibleText(main);

        if (!text) {
            speak("There is nothing on this page to read.");
            return;
        }
        // Long pages are summarised by their headings rather than read in full.
        const headings = [...main.querySelectorAll("h1, h2")]
            .map((h) => h.innerText.trim())
            .filter(Boolean);
        if (text.length > 900 && headings.length) {
            speak(`${document.title}. This page covers: ${headings.slice(0, 8).join(". ")}.`);
        } else {
            speak(text.slice(0, 1600), { force: true });
        }
    }

    // ---- confirmation flow -------------------------------------------------
    function setPending(plan) {
        state.pending = plan;
        panel("pending", `${plan.speak || "Confirm this action?"}`);
        const yes = document.querySelector("[data-voice-confirm-yes]");
        const no = document.querySelector("[data-voice-confirm-no]");
        if (yes) yes.focus();
        if (no) no.removeAttribute("hidden");
    }

    async function confirmPending() {
        const plan = state.pending;
        if (!plan) return;
        state.pending = null;
        hideConfirm();
        try {
            await plan.run();
            panel("status", "Done.");
            speak("Done.", { force: true });
            // Captures redirect server-side; reload so the page reflects it.
            setTimeout(() => window.location.reload(), 700);
        } catch (err) {
            panel("status", "That did not go through.");
            speak("That did not go through. Nothing was changed.");
        }
    }

    function cancelPending() {
        state.pending = null;
        hideConfirm();
        panel("status", "Cancelled. Nothing was changed.");
        speak("Cancelled. Nothing was changed.", { force: true });
    }

    function hideConfirm() {
        const no = document.querySelector("[data-voice-confirm-no]");
        if (no) no.hidden = true;
        panel("pending", "");
    }

    // ---- UI ----------------------------------------------------------------
    let panelTimer = null;

    function panel(kind, text) {
        const node = document.querySelector("[data-voice-body]");
        if (!node) return;
        node.textContent = text || "";
        node.dataset.kind = kind || "";
        const wrap = document.querySelector("[data-voice-panel]");
        if (wrap) wrap.classList.toggle("is-open", Boolean(text));
        clearTimeout(panelTimer);
        if (kind === "status" || kind === "answer") {
            panelTimer = setTimeout(() => {
                node.textContent = "";
                if (wrap) wrap.classList.remove("is-open");
            }, 12000);
        }
    }

    function showAnswerPanel(payload) {
        const box = document.querySelector("[data-voice-answer]");
        if (!box) return;
        box.innerHTML = "";
        box.hidden = false;
        const head = document.createElement("div");
        head.className = "voice-answer-head";
        const intent = document.createElement("strong");
        intent.textContent = (payload.intent || "answer").replace(/_/g, " ");
        const basis = document.createElement("span");
        basis.className = payload.grounded ? "basis-tag" : "basis-tag warn";
        basis.textContent = payload.grounded ? "grounded" : "not enough data";
        head.append(intent, basis);
        const body = document.createElement("p");
        body.textContent = payload.answer;
        box.append(head, body);
        if ((payload.citations || []).length) {
            const cites = document.createElement("small");
            cites.textContent = `Based on ${payload.citations.length} of your records.`;
            box.append(cites);
        }
        const link = document.createElement("a");
        link.className = "link";
        link.href = "/copilot";
        link.textContent = "See in Copilot history";
        box.append(link);
    }

    function toast(message) {
        const region = document.querySelector("[data-toast-region]");
        if (!region) return;
        const node = document.createElement("div");
        node.className = "toast";
        node.textContent = message;
        region.appendChild(node);
        setTimeout(() => node.remove(), 3200);
    }

    function sync() {
        document.body.classList.toggle("voice-listening", state.listening);
        document.body.classList.toggle("voice-speaking", state.speaking);
        const btn = document.querySelector("[data-voice-toggle]");
        if (btn) {
            btn.setAttribute("aria-pressed", String(state.listening));
            btn.title = state.listening ? "Stop listening" : "Start voice commands";
        }
        const speakBtn = document.querySelector("[data-voice-speak-toggle]");
        if (speakBtn) {
            speakBtn.setAttribute("aria-pressed", String(state.speakReplies));
            speakBtn.title = state.speakReplies ? "Spoken replies on" : "Spoken replies off";
        }
    }

    // ---- speech recognition -------------------------------------------------
    // One recognition session per user gesture. Never restarted.
    //
    // The earlier version re-opened the session from a setTimeout whenever
    // Chrome reported `no-speech`. That was the bug: Chrome had not finished
    // releasing the microphone, so the new start() threw InvalidStateError,
    // the catch retried again, and the session was torn down and rebuilt in a
    // loop. The mic light stayed on and no audio was ever delivered - which
    // looks identical to "the microphone does not work", even though the
    // microphone is fine everywhere else.
    //
    // So: start once, from the click itself (which keeps the user gesture
    // Chrome wants), stay open with continuous = true, and close the session
    // ourselves once speech has been heard and the speaker pauses.
    const SILENCE_AFTER_SPEECH_MS = 1400; // pause that ends an utterance
    const GIVE_UP_AFTER_MS = 12000;       // open mic with nothing at all
    const MAX_UTTERANCE_MS = 20000;

    const ERROR_TEXT = {
        "not-allowed": "Microphone permission is blocked for this site. Click the padlock in the address bar, set the microphone to Allow, then press the mic again.",
        "service-not-allowed": "The browser blocked the microphone for this site. Allow it in site settings, then press the mic again.",
        "audio-capture": "No microphone was found. Check that one is connected and not muted in Windows sound settings.",
        network: "Your browser could not reach its speech service. Chrome's voice input streams audio to the internet, so a proxy, VPN, or strict firewall will block it. Speech output and typing still work.",
        "language-not-supported": "This browser does not support voice input for the selected language.",
    };

    function startListening() {
        if (!hasSpeechInput) {
            offerTyping("This browser has no voice input (Firefox does not implement it). You can type your command instead.");
            return;
        }
        // Microphone capture only runs in a secure context. On http:// over a LAN
        // address the API exists but never delivers audio.
        if (!window.isSecureContext) {
            offerTyping("Voice input needs a secure connection. Open the app on localhost or https, or type your command instead.");
            return;
        }
        if (state.listening) { stopListening(); return; }

        stopSpeaking();
        closeSession();          // make sure no previous session is still holding the mic

        const recognition = new Recognition();
        recognition.lang = document.documentElement.lang || "en-US";
        recognition.interimResults = true;
        // Keep the session open so a normal pause does not end it. The browser
        // will not restart it for us, so we close it explicitly below.
        recognition.continuous = true;
        recognition.maxAlternatives = 1;

        const startedAt = Date.now();
        let heard = "";        // finalised speech for this utterance
        let interim = "";      // in-progress speech
        let closing = false;   // set once we have decided to submit

        const finish = () => {
            if (closing) return;
            closing = true;
            const transcript = (heard || interim).trim();
            const silenceTimer = state.silenceTimer;
            state.silenceTimer = null;
            state.listening = false;
            sync();
            // Close the session before acting, so the microphone is released
            // before anything else tries to use it.
            closeSession();
            if (transcript) {
                handleTranscript(transcript);
            } else {
                panel("error", noSpeechMessage());
                showTypeBox();
            }
            void silenceTimer;
        };

        // Once we have heard something, a pause means the utterance is over.
        const scheduleClose = () => {
            clearTimeout(state.silenceTimer);
            state.silenceTimer = setTimeout(finish, SILENCE_AFTER_SPEECH_MS);
        };

        // Guard rail: the mic stays open but the speaker never said anything.
        state.giveUpTimer = setTimeout(() => {
            if (!heard && !interim) finish();
        }, GIVE_UP_AFTER_MS);

        recognition.onstart = () => {
            state.listening = true;
            sync();
            panel("listening", "Listening — speak now.");
        };

        recognition.onresult = (event) => {
            for (let i = event.resultIndex; i < event.results.length; i += 1) {
                const result = event.results[i];
                const chunk = result[0].transcript;
                if (result.isFinal) {
                    heard += `${chunk} `;
                    interim = "";
                    panel("transcript", heard.trim());
                    scheduleClose();
                } else {
                    interim += chunk;
                    // Show words appearing live, so it is obvious the mic is
                    // actually capturing audio.
                    panel("transcript", `${(heard + interim).trim()} …`);
                }
            }
            if (Date.now() - startedAt > MAX_UTTERANCE_MS) finish();
        };

        recognition.onerror = (event) => {
            clearTimeout(state.giveUpTimer);
            clearTimeout(state.silenceTimer);
            closing = true;
            state.listening = false;
            sync();

            if (event.error === "no-speech") {
                panel("error", noSpeechMessage());
                showTypeBox();
                return;
            }
            if (event.error === "aborted") return; // we closed it deliberately

            const message = ERROR_TEXT[event.error]
                || `Voice input failed (${event.error}). Press the mic to try again.`;
            offerTyping(message);
        };

        recognition.onend = () => {
            // Fires after stop()/abort() and after the browser's own silence
            // timeout. If speech arrived, submit it; otherwise say why it was
            // empty. Never re-start here - that was the original defect.
            if (closing) return;
            clearTimeout(state.giveUpTimer);
            clearTimeout(state.silenceTimer);
            const transcript = (heard || interim).trim();
            closing = true;
            state.listening = false;
            sync();
            if (transcript) {
                handleTranscript(transcript);
            } else {
                panel("error", noSpeechMessage());
                showTypeBox();
            }
        };

        state.recognition = recognition;
        try {
            recognition.start();
        } catch (err) {
            closing = true;
            clearTimeout(state.giveUpTimer);
            offerTyping("The microphone could not be started. Close other apps that may be using it, then press the mic again.");
        }
    }

    // Why the microphone opened but delivered nothing. Ordered by likelihood,
    // so the message points at the thing most worth checking first.
    function noSpeechMessage() {
        if (!window.isSecureContext) {
            return "Voice input needs a secure connection. Open the app on localhost or https, or type your command.";
        }
        if (navigator.onLine === false) {
            return "You appear to be offline. Chrome's voice input needs an internet connection, so type your command instead.";
        }
        return "The microphone opened but nothing was recognised. If voice works in other apps, check that this tab has microphone permission (padlock > Microphone), then press the mic and speak immediately. You can also type your command.";
    }

    // Releases the microphone. Must be called before starting a new session,
    // because Chrome refuses start() while a session is still active.
    function closeSession() {
        clearTimeout(state.giveUpTimer);
        clearTimeout(state.silenceTimer);
        state.giveUpTimer = null;
        state.silenceTimer = null;
        const recognition = state.recognition;
        state.recognition = null;
        if (recognition) {
            try { recognition.stop(); } catch (err) { /* already stopped */ }
            // abort() releases the hardware immediately; stop() only asks.
            setTimeout(() => {
                try { recognition.abort(); } catch (err) { /* already gone */ }
            }, 0);
        }
    }

    function stopListening() {
        closeSession();
        state.listening = false;
        sync();
    }// ---- typing fallback ----------------------------------------------------
    // Shown whenever voice input is unavailable or keeps failing, so the
    // feature degrades to "type a command" rather than to nothing.
    function offerTyping(message) {
        panel("error", message);
        showTypeBox();
    }

    function showTypeBox() {
        const box = document.querySelector("[data-voice-typebox]");
        if (box) box.hidden = false;
    }

    function submitTyped(text) {
        const box = document.querySelector("[data-voice-typebox]");
        if (box) {
            box.hidden = true;
            const input = box.querySelector("input");
            if (input) input.value = "";
        }
        const clean = (text || "").trim();
        if (clean) handleTranscript(clean);
    }

    function stopListening() {
        if (state.recognition) {
            try { state.recognition.stop(); } catch (err) { /* already stopped */ }
        }
        state.listening = false;
        sync();
    }

    // ---- transcript handling ------------------------------------------------
    // A bare yes/no with nothing to confirm is a normal thing to say, not an
    // unknown question — answering it with "I don't recognise that" reads as
    // broken, so it gets its own message.
    const AFFIRMATIVE = /^(?:yes|yeah|yep|confirm|do it|go ahead|sure|ok|okay|please do)\b/i;
    const NEGATIVE = /^(?:no|nope|cancel|stop that|don't|do not)\b/i;

    function handleTranscript(transcript) {
        const plan = route(transcript);

        if (!plan) {
            if (AFFIRMATIVE.test(transcript) || NEGATIVE.test(transcript)) {
                panel("status", "Nothing is waiting for confirmation.");
                speak("Nothing is waiting for confirmation.");
                return;
            }
            // Not a known command: treat it as a question rather than failing.
            // The copilot still refuses what it cannot know, so this is safe.
            panel("transcript", transcript);
            askCopilot(transcript);
            return;
        }

        panel("transcript", transcript);

        if (plan.mutating) {
            setPending(plan);
            speak(plan.speak, { force: true });
            return;
        }

        speak(plan.speak, { force: true });
        plan.run();
    }

    // ---- public surface -----------------------------------------------------
    function init() {
        if (!hasSpeechInput && !hasSpeechOutput) return;

        const mount = document.createElement("div");
        mount.className = "voice-dock";
        mount.setAttribute("data-voice-ui", "");
        mount.innerHTML = `
            <div class="voice-panel" data-voice-panel>
                <p class="voice-body" data-voice-body></p>
                <form class="voice-typebox" data-voice-typebox hidden>
                    <input type="text" name="voice-command" autocomplete="off"
                           placeholder="Type a command, e.g. what should I do">
                    <button class="btn ghost small" type="submit">Go</button>
                </form>
                <div class="voice-answer" data-voice-answer hidden></div>
                <div class="voice-confirm" data-voice-confirm-no hidden>
                    <button class="btn ghost small" type="button" data-voice-confirm-yes>Yes, do it</button>
                    <button class="btn ghost small" type="button" data-voice-cancel>No, cancel</button>
                </div>
            </div>
            <div class="voice-buttons">
                ${hasSpeechInput ? `
                <button class="voice-btn" type="button" data-voice-toggle aria-pressed="false" title="Start voice commands">
                    <span class="voice-mic" aria-hidden="true"></span>
                    <span class="sr-only">Start voice commands</span>
                </button>` : ""}
                ${hasSpeechOutput ? `
                <button class="voice-btn voice-btn-small" type="button" data-voice-speak-toggle aria-pressed="true" title="Spoken replies on">
                    <span aria-hidden="true">🔊</span>
                    <span class="sr-only">Toggle spoken replies</span>
                </button>` : ""}
                <button class="voice-btn voice-btn-small" type="button" data-voice-read title="Read this page aloud">
                    <span aria-hidden="true">📖</span>
                    <span class="sr-only">Read this page aloud</span>
                </button>
            </div>
        `;
        document.body.appendChild(mount);

        mount.querySelectorAll("[data-voice-toggle]").forEach((b) =>
            b.addEventListener("click", startListening));
        mount.querySelectorAll("[data-voice-read]").forEach((b) =>
            b.addEventListener("click", readPage));
        const speakToggle = mount.querySelector("[data-voice-speak-toggle]");
        if (speakToggle) {
            speakToggle.addEventListener("click", () => {
                state.speakReplies = !state.speakReplies;
                if (!state.speakReplies) stopSpeaking();
                sync();
                toast(state.speakReplies ? "Spoken replies on" : "Spoken replies off");
            });
        }
        const yes = mount.querySelector("[data-voice-confirm-yes]");
        if (yes) yes.addEventListener("click", confirmPending);
        const cancel = mount.querySelector("[data-voice-cancel]");
        if (cancel) cancel.addEventListener("click", cancelPending);

        const typebox = mount.querySelector("[data-voice-typebox]");
        if (typebox) {
            typebox.addEventListener("submit", (event) => {
                event.preventDefault();
                submitTyped(typebox.querySelector("input").value);
            });
        }

        // Push-to-talk on Space, releasing to submit — held so it never fires
        // while the creator is typing into a form.
        let spaceHeld = false;
        document.addEventListener("keydown", (event) => {
            if (event.code !== "Space" || event.repeat) return;
            const tag = (event.target.tagName || "").toLowerCase();
            if (tag === "input" || tag === "textarea" || event.target.isContentEditable) return;
            event.preventDefault();
            spaceHeld = true;
            startListening();
        });
        document.addEventListener("keyup", (event) => {
            if (event.code !== "Space" || !spaceHeld) return;
            const tag = (event.target.tagName || "").toLowerCase();
            if (tag === "input" || tag === "textarea" || event.target.isContentEditable) return;
            spaceHeld = false;
            stopListening();
        });

        sync();
    }

    return {
        init,
        speak,
        stopSpeaking,
        startListening,
        stopListening,
        readPage,
        hasSpeechInput,
        hasSpeechOutput,
        // surfaced so the cause of a voice failure can be reported precisely
        diagnostics() {
            return {
                speechInput: hasSpeechInput,
                speechOutput: hasSpeechOutput,
                secureContext: Boolean(window.isSecureContext),
                // Chrome's recogniser streams audio to its own speech service,
                // so a blocked network shows up as a failure here
                online: navigator.onLine,
                userAgent: navigator.userAgent,
            };
        },
        // exposed for verification
        _route: route,
        _toSpeech: toSpeech,
        _submitTyped: submitTyped,
    };
})();

document.addEventListener("DOMContentLoaded", () => Voice.init());