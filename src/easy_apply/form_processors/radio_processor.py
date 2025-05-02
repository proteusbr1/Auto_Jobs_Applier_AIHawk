# src/easy_apply/form_processors/radio_processor.py
"""
Processor for radio-button groups in LinkedIn Easy Apply forms.

Handles identifying radio button groups, extracting options, determining the
appropriate selection using cache or LLM, and interacting with the elements.

Key points in this version
──────────────────────────
1. **No stale references** – we never cache `WebElement` handles for the
   individual inputs/labels.  Only the surrounding `<fieldset>` survives
   between retries; every click attempt re-locates fresh elements.
2. **Single selector table** comes from `BaseProcessor.SELECTORS`.
3. **Shared answer logic** is borrowed from `DropdownProcessor`.
4. **Extensive logging** (TRACE/DEBUG/INFO/WARNING/ERROR) to aid debugging.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional, TYPE_CHECKING, Tuple

from loguru import logger
from selenium.common.exceptions import (
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC

from .base_processor import BaseProcessor

if TYPE_CHECKING:                       # — type-only imports
    from src.job import Job
else:
    Job: Any = object                   # noqa: N818  (runtime placeholder)


# ---------------------------------------------------------------------------#
#  Drop-in stub in case `DropdownProcessor` cannot be imported (unit tests)   #
# ---------------------------------------------------------------------------#
try:
    from .dropdown_processor import DropdownProcessor
except ImportError:                                                          # pragma: no cover
    logger.warning("DropdownProcessor not found – using minimal stub")

    class DropdownProcessor(BaseProcessor):       # type: ignore[override]
        """Extremely small fallback that always returns the first option."""

        def _get_answer_for_options(             # noqa: D401  (private helper)
            self,
            question_text: str,
            question_type: str,
            options: List[str],
            job: Job,
        ) -> Optional[str]:
            return options[0] if options else None


# ---------------------------------------------------------------------------#
#                                Main class                                  #
# ---------------------------------------------------------------------------#
class RadioProcessor(BaseProcessor):
    """
    Processor for `<input type="radio">` clusters (both old & new LinkedIn UI).
    """

    # ──────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────
    def handle(self, section: WebElement, job: Job) -> bool:  # noqa: D401
        """
        Scan *section* for radio-button field-sets and answer them.

        Returns ``True`` if one (or more) radio group was successfully handled.
        """
        logger.debug("RadioProcessor → scanning section for radio groups")
        handled = False

        # ---------- 1. Try the “new” UI structure ---------------------------------
        try:
            fieldsets = section.find_elements(
                By.CSS_SELECTOR, self.selectors["new"]["radio_fieldset"]
            )
        except StaleElementReferenceException:
            logger.warning("Section went stale before we could search for fieldsets")
            return False

        for fieldset in fieldsets:
            if self._handle_new_radio_structure(fieldset, job):
                handled = True

        # ---------- 2. Fallback: legacy class-based structure ---------------------
        if not handled:
            handled = self._handle_old_radio_structure(section, job)

        if not handled:
            logger.trace("No radio buttons processed in this section")
        return handled

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers – NEW LinkedIn layout
    # ──────────────────────────────────────────────────────────────────────
    # Helper para extrair o texto visível do label
    @staticmethod
    def _extract_label_text(box: WebElement) -> Optional[str]:
        """
        Devolve o texto do <label> de uma opção, cobrindo as duas variações
        de markup que o LinkedIn usa atualmente.
        """
        try:
            lbl = box.find_element(
                By.XPATH, ".//label[@data-test-text-selectable-option__label]"
            )
        except NoSuchElementException:
            try:
                lbl = box.find_element(By.TAG_NAME, "label")
            except NoSuchElementException:
                return None
        return (lbl.text or "").strip() or None

    def _handle_new_radio_structure(self, fieldset: WebElement, job: Job) -> bool:
        try:
            legend = fieldset.find_element(By.TAG_NAME, "legend")
            raw_question = self.driver.execute_script(
                "return arguments[0].textContent;", legend
            ).strip()
            question = self.answer_storage.sanitize_text(raw_question)
            logger.debug(f"New-UI radio question → '{question}'")

            # Coleta das opções (robusta)
            containers = fieldset.find_elements(
                By.CSS_SELECTOR, self.selectors["new"]["radio_option_container"]
            )
            labels = [txt for box in containers if (txt := self._extract_label_text(box))]
            if len(labels) < 2:
                logger.warning("Menos de duas opções detectadas – pulando")
                return False

            answer = DropdownProcessor(
                self.driver, self.llm_processor,
                self.answer_storage, self.wait_time
            )._get_answer_for_options(question, "radio", labels, job)

            if not answer:
                logger.error(f"Sem resposta determinada para “{question}”.")
                return False

            if self._select_radio_option(fieldset, answer):
                self.save_answer(question, "radio", answer)
                logger.info(f"Respondido '{question}' → '{answer}'")
                return True
            return False

        except StaleElementReferenceException:
            logger.warning("Fieldset ficou stale – recomeçar no próximo loop")
            return False
        except Exception as exc:
            logger.error(f"Erro inesperado no handler novo: {exc!r}", exc_info=True)
            return False


    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers – OLD layout (class-based)
    # ──────────────────────────────────────────────────────────────────────
    def _handle_old_radio_structure(self, section: WebElement, job: Job) -> bool:
        """
        Very similar to the new handler but relies on legacy class names.
        """
        try:
            options = section.find_elements(
                By.CSS_SELECTOR, f".{self.selectors['old']['radio_option']}"
            )
            if len(options) < 2:
                return False

            question = self.extract_question_text(section)
            logger.debug(f"Old-UI radio question → '{question}'")

            labels: List[str] = []
            for opt in options:
                txt = opt.text.strip()
                if txt:
                    labels.append(txt)

            if not labels:
                logger.warning("Old-UI: no labels detected – aborting")
                return False

            answer = DropdownProcessor(
                self.driver, self.llm_processor, self.answer_storage, self.wait_time
            )._get_answer_for_options(question, "radio", labels, job)  # type: ignore

            if not answer:
                return False

            # find the matching option again and click via JS
            try:
                target = section.find_element(
                    By.XPATH,
                    f".//*[self::label or self::div][normalize-space()='{answer}']",
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});"
                    "arguments[0].click();",
                    target,
                )
                logger.info(f"Old-UI: clicked option '{answer}'")
                self.save_answer(question, "radio", answer)
                return True
            except Exception as click_err:
                logger.error(f"Click failed in old-UI handler: {click_err!r}")

            return False

        except StaleElementReferenceException:
            logger.warning("Section became stale in old-UI handler")
            return False
        except Exception as exc:
            logger.error(f"Unhandled error in old-UI handler: {exc!r}", exc_info=True)
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Unified selection routine (no stale references)
    # ──────────────────────────────────────────────────────────────────────
    def _select_radio_option(self, fieldset: WebElement, answer: str) -> bool:
        """
        Seleciona a opção pedida, tentando primeiro pelo texto visível
        e, se necessário, pelo atributo value.
        """
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            logger.trace(f"Tentativa {attempt} de clicar em '{answer}'")
            try:
                # (a) Procurar label com texto exato
                try:
                    lbl = fieldset.find_element(
                        By.XPATH, f'.//label[normalize-space()="{answer}"]'
                    )
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", lbl
                    )
                    self.driver.execute_script("arguments[0].click();", lbl)
                except NoSuchElementException:
                    # (b) Fallback no input[value]
                    inp = fieldset.find_element(
                        By.CSS_SELECTOR, f'input[type="radio"][value="{answer}"]'
                    )
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", inp
                    )
                    self.driver.execute_script("arguments[0].click();", inp)

                # Confirma se algum input está marcado
                if fieldset.find_elements(
                    By.XPATH, ".//input[@type='radio' and @checked]"
                ):
                    logger.debug(f"Radio '{answer}' selecionado com sucesso")
                    return True

            except Exception as exc:
                logger.debug(f"Falhou na tentativa {attempt}: {exc!r}")

            time.sleep(0.4 * attempt)

        logger.error(f"Não foi possível escolher '{answer}' após {MAX_RETRIES} tentativas")
        return False
