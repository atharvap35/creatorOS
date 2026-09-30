import os

from fastapi.templating import Jinja2Templates

from app.currency import current_currency, money, money_compact, symbol

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

templates.env.globals["money"] = money
templates.env.globals["money_compact"] = money_compact
templates.env.globals["currency_symbol"] = symbol
templates.env.globals["active_currency"] = lambda: current_currency.get()
