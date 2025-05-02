#!/usr/bin/env bash
#
# script de orquestração para cron **ou** execução manual
# Autor: você 😉 | Atualizado: 2025-05-01
# -----------------------------------------------------------------------------

PROJECT_DIR="/home/proteusbr/Auto_Jobs_Applier_AIHawk"
VENV_PATH="$PROJECT_DIR/.venv"
LOCK_FILE="/var/lock/run_auto_jobs.lock"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"
CHROME_PROFILE="$PROJECT_DIR/chrome_profile/default_user"
LOCK_ARTIFACTS=("SingletonLock" "SingletonCookie" "SingletonSocket")

# -----------------------------------------------------------------------------
# Funções utilitárias
# -----------------------------------------------------------------------------
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

cleanup_chrome_locks() {
  echo "[$(timestamp)] Limpando locks residuais do perfil Chrome…"
  for f in "${LOCK_ARTIFACTS[@]}"; do
    if [ -e "$CHROME_PROFILE/$f" ]; then
      rm -f "$CHROME_PROFILE/$f"
      echo "[$(timestamp)]   • Removido $f"
    fi
  done
}

kill_running_chrome() {
  if pgrep chrome >/dev/null; then
    echo "[$(timestamp)] Encerrando processos Chrome em execução…"
    pkill chrome
    sleep 5
  fi
}

# -----------------------------------------------------------------------------
# Ambiente mínimo para execuções headless (cron, systemd, Docker etc.)
# -----------------------------------------------------------------------------
export HEADLESS=true        # força chrome_browser_options() → --headless
export WDM_LOG_LEVEL=0      # silencia webdriver-manager
unset DISPLAY               # garante ausência de X-server

# -----------------------------------------------------------------------------
# Início — redirecionamento de log e flock para evitar sobreposição
# -----------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

(
  # flock -w 120 -n 9 || { echo "[$(timestamp)] Outro processo ainda está rodando — abortando."; exit 0; }

  echo "--------------------- $(timestamp) ---------------------"

  cd "$PROJECT_DIR" || { echo "[$(timestamp)] ERRO: diretório do projeto não encontrado."; exit 1; }

  # --- Pré-execução -----------------------------------------------------------
  kill_running_chrome
  cleanup_chrome_locks

  # --- Virtualenv -------------------------------------------------------------
  if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
  else
    echo "[$(timestamp)] ERRO: virtualenv não encontrado em $VENV_PATH"; exit 1;
  fi

  # --- Execução principal -----------------------------------------------------
  echo "[$(timestamp)] Iniciando main.py…"
  python main.py
  EXIT_CODE=$?

  # --- Pós-execução -----------------------------------------------------------
  echo "[$(timestamp)] main.py finalizou com código $EXIT_CODE"
  echo "[$(timestamp)] Rodando log_manager…"
  python log_manager.py --consolidate-cron --rotate-cron --max-cron-size 500 || echo "[$(timestamp)] Aviso: falha no log_manager"

  deactivate
  echo "[$(timestamp)] Fim do script."
) 9>"$LOCK_FILE"
