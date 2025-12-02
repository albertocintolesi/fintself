import time
from decimal import Decimal
from typing import List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from fintself.core.exceptions import DataExtractionError, LoginError
from fintself.core.models import MovementModel, PortfolioModel, StockModel
from fintself.scrapers.base import BaseScraper
from fintself.utils.logging import logger
from fintself.utils.parsers import parse_chilean_amount, parse_chilean_date


class RacionalScraper(BaseScraper):
    """Scraper to extract movements from Racional App"""

    LOGIN_URL = "https://app.racional.cl/login"

    def _get_bank_id(self) -> str:
        return "cl_racional"

    def _init_login(self) -> str:
        """
        Performs the first step of login: enters credentials and waits for 2FA screen.
        """
        assert self.user is not None, "User must be provided"
        assert self.password is not None, "Password must be provided"

        page = self._ensure_page()
        logger.info("Logging into Racional App.")

        self._navigate(self.LOGIN_URL)

        email_selector = "input[type='email']"
        password_selector = "input[type='password']"

        try:
            self._wait_for_selector(email_selector, timeout_override=30000)
        except Exception:
            raise LoginError("Failed to load login page")

        logger.info("Entering credentials.")
        self._type(email_selector, self.user, delay=100)
        self._type(password_selector, self.password, delay=100)

        logger.info("Submitting login form.")
        submit_selector = "button:has-text('Iniciar sesión')"

        try:
            page.locator(submit_selector).wait_for(
                state="enabled", timeout=5000)
        except Exception:
            logger.warning("Submit button check timed out, clicking anyway...")

        self._click(submit_selector)

        logger.info("Checking login result...")

        verify_code_selector = "button:has-text('Verificar Código')"
        dashboard_selector = "text='Total Inversiones'"

        try:
            self._wait_for_selector(
                verify_code_selector, timeout_override=10000)

            self._save_debug_info("05_login_code_needed")
            logger.info("2FA screen detected. Code required.")
            return "CODE_REQUIRED"

        except (PlaywrightTimeoutError, DataExtractionError):
            logger.info(
                "2FA screen not found. Checking for direct dashboard access...")

            try:
                self._wait_for_selector(
                    dashboard_selector, timeout_override=10000)

                self._save_debug_info("05_login_direct_success")
                logger.info("Direct login successful (No 2FA required).")
                return "SUCCESS"

            except (PlaywrightTimeoutError, DataExtractionError):
                self._save_debug_info("init_login_failed")
                raise LoginError(
                    "Login failed: Neither 2FA screen nor Dashboard appeared.")

    def _complete_login(self, code: str) -> None:
        """
        Performs the second step of login:
        Enters autentication code and navigates to dashboard.
        """
        page = self._ensure_page()
        logger.info(f"Entering 2FA code: {code}")

        code_input_selector = "input.otp-input__control"
        verify_button_selector = "button:has-text('Verificar')"

        try:
            self._wait_for_selector(
                code_input_selector, timeout_override=10000)
            self._fill(code_input_selector, code)
            page.wait_for_timeout(500)
            self._click(verify_button_selector)

        except Exception as e:
            raise LoginError(f"Error entering 2FA code: {e}")

        try:
            dashboard_selector = "text='Total Inversiones'"
            self._wait_for_selector(dashboard_selector, timeout_override=30000)
            logger.info("2FA verification successful. Logged in.")
            self._save_debug_info("06_login_complete")
        except Exception:
            self._save_debug_info("login_failed_after_code")
            raise LoginError(
                "Failed to access dashboard after entering 2FA code.")

    def _login(self):
        """Orchestrates multistep login for Racional App"""
        status = self._init_login()

        if status == "CODE_REQUIRED":
            print("\n" + "="*50)
            print("⚠️  RACIONAL REQUIERE AUTENTICACIÓN DE DOS FACTORES ⚠️")
            code = input(
                ">> Por favor, ingresa el código enviado a tu correo: ")
            print("="*50 + "\n")

            self._complete_login(code)

    def _close_popup(self) -> None:
        """Closes marketing popup if it appears."""

        try:
            page = self._ensure_page()
            logger.info("Checking for marketing popup.")

            popup_close_button = page.locator("button:has-text('Confirmar')")

            if popup_close_button.is_visible(timeout=5000):
                logger.info("Popup detected. Attempting to close...")
                self._click(popup_close_button)
                logger.info("Marketing popup closed successfully.")
                self._save_debug_info("07_popup_closed")
                page.wait_for_timeout(1000)
            else:
                logger.info("No marketing popup found (skipped).")

        except Exception as e:
            logger.warning(f"Ignored error while checking popup: {e}")

    def _extract_stock(self) -> Optional[StockModel]:
        """
        Extrae la información detallada (Cantidad, Costo) desde la vista de detalle.
        Asume que ya estamos dentro de la página del stock.
        """
        page = self._ensure_page()
        try:
            info_container_selector = "div.columns-container.asset-info"
            page.wait_for_selector(info_container_selector, timeout=30000)

            def get_value_by_title(title: str) -> str:
                return page.locator(
                    f"div.share.asset-property:has(h5:has-text('{title}')) p.asset-property-value"
                ).inner_text().strip()

            quantity_text = get_value_by_title("Acciones")
            avg_cost_text = get_value_by_title("Costo promedio")

            clean_qty = quantity_text.replace(",", ".")
            quantity = Decimal(clean_qty)

            clean_cost = avg_cost_text.replace("US$", "").replace(
                ".", "").replace(",", ".").strip()
            average_cost = Decimal(clean_cost)

            return StockModel(
                symbol="PENDING",
                quantity=quantity,
                average_cost=average_cost,
                currency="USD"
            )

        except Exception as e:
            logger.error(f"Error extracting stock details: {e}")
            return None

    def _scrape_portfolio(self) -> List[PortfolioModel]:
        """Orchestrates the extraction of portfolio data using Scan & Jump strategy."""
        page = self._ensure_page()
        logger.info("Starting portfolio extraction...")

        # --- 1. OPTIMIZACIÓN: Bloquear recursos pesados ---
        try:
            page.route("**/*.{png,jpg,jpeg,svg,woff,woff2,gif}",
                       lambda route: route.abort())
        except Exception:
            pass

        # --- 2. NAVEGACIÓN INICIAL (Lógica original) ---
        stocks_header = "h2.heading-text"
        stocks_button = page.locator(selector=stocks_header, has_text="Stocks")

        try:
            logger.info("Navigating to stocks...")
            self._click(stocks_button, timeout_override=10000)
            self._save_debug_info("08_stock_list")

            stock_list_selector = "text='Mis Stocks'"
            self._wait_for_selector(
                stock_list_selector, timeout_override=30000)
            logger.info("Navigation to stock list completed.")

        except (PlaywrightTimeoutError, DataExtractionError) as e:
            self._save_debug_info("navigate_to_stocks_failed")
            raise DataExtractionError(f"Failed to navigate to stock list: {e}")

        logger.info("Extracting wallet USD amount...")
        wallet_usd = Decimal("0")
        try:
            wallet_selector = "div.summary-value:has-text('Poder de Compra') .summary-amount"
            self._wait_for_selector(wallet_selector, timeout_override=10000)
            wallet_text = page.locator(wallet_selector).inner_text().strip()
            clean_text = wallet_text.replace(
                "US$", "").replace(" ", "").replace(",", ".")
            wallet_usd = Decimal(clean_text)
            logger.info(f"Wallet Balance extracted: {wallet_usd} USD")
        except Exception as e:
            self._save_debug_info("wallet_extraction_failed")
            logger.warning(f"Could not extract wallet balance: {e}")

        # --- 3. EXPANDIR LISTA (Lógica original) ---
        stocks: List[StockModel] = []

        logger.info("Expanding full stock list...")
        try:
            expand_button_selector = "button.expand-button:has-text('Ver más')"
            if page.locator(expand_button_selector).is_visible(timeout=10000):
                logger.info("Clicking 'Ver más' to load more stocks...")
                self._click(expand_button_selector)
        except (PlaywrightTimeoutError, DataExtractionError) as e:
            self._save_debug_info("stock_list_load_failed")
            raise DataExtractionError(
                f"Could not load complete list of stocks: {e}")

        # --- 4. ESCANEAR TICKERS ---
        stock_card_selector = "app-stock-card"
        # Esperamos visibles para asegurar que cargaron tras el clic
        page.wait_for_selector(f"{stock_card_selector}:visible", timeout=10000)

        # Capturamos los elementos para leer sus IDs
        cards = page.locator(stock_card_selector).all()
        tickers_to_process = []

        for card in cards:
            ticker = card.get_attribute("data-asset-id")
            if ticker:
                tickers_to_process.append(ticker)

        total_stocks = len(tickers_to_process)
        logger.info(
            f"Found {total_stocks} tickers to process: {tickers_to_process}")

        # --- 5. BUCLE DE NAVEGACIÓN DIRECTA (JUMP) ---
        for i, ticker in enumerate(tickers_to_process):
            logger.info(f"Processing stock {i+1}/{total_stocks}: {ticker}")

            try:
                # Navegación directa usando el patrón conocido
                target_url = f"https://app.racional.cl/asset-details/{ticker}?home=true"
                logger.debug(f"Jumping to: {target_url}")
                page.goto(target_url)

                # Extraer Datos (Usando el método original de selectores)
                stock_data = self._extract_stock()

                if stock_data:
                    stock_data.symbol = ticker
                    stocks.append(stock_data)
                else:
                    logger.warning(f"Failed to extract data for {ticker}")

            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                continue

        return PortfolioModel(
            wallet_balance_usd=wallet_usd,
            stocks=stocks
        )

    def _scrape_movements(self) -> List[MovementModel]:
        """
        Abstract class base scraping method, not used
        in Racional App.
        """
        return []
