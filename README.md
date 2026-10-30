# Canti in Chiesa — proiezione su Raspberry Pi

Server REST leggero, senza dipendenze Python esterne, gestito come progetto [uv](https://docs.astral.sh/uv/). Il Raspberry Pi riceve il testo e lo impagina localmente; il browser del Pi mostra le slide su HDMI. La proiezione è bianca su nero, centrata e leggibile, con 2–4 righe per slide.

## Hardware consigliato

Raspberry Pi 4 Model B con 2 GB di RAM, Raspberry Pi OS Desktop 64-bit e collegamento HDMI0 → proiettore. È più che sufficiente per testo in Full HD. Il Pi va collegato alla rete Ethernet o Wi-Fi della parrocchia; assegnargli un indirizzo DHCP riservato rende stabile il collegamento SSH.

## API

Il server ascolta solo su `127.0.0.1:8787`, così la porta REST non è esposta in rete. Dal computer di regia apri un tunnel:

```sh
ssh -N -L 8787:127.0.0.1:8787 pi@IP_DEL_RASPBERRY
```

Lascia il tunnel aperto. Le chiamate REST locali al computer (`http://127.0.0.1:8787`) arrivano al Pi. Il testo usa righe separate e righe vuote per separare le strofe. La risposta di `/api/song/load` include le slide create e il numero di pagine.

1. Avvia una nuova canzone (opzionale titolo):

```sh
curl -X POST http://127.0.0.1:8787/api/song/start \
  -H 'Content-Type: application/json' -d '{"title":"Il Signore è il mio pastore"}'
```

2. Carica il testo, non immagini o slide precalcolate:

```sh
curl -X POST http://127.0.0.1:8787/api/song/load \
  -H 'Content-Type: application/json' \
  -d '{"title":"Il Signore è il mio pastore","lyrics":"Il Signore è il mio pastore,\\nnon manco di nulla.\\n\\nSu pascoli erbosi mi fa riposare,\\nad acque tranquille mi conduce."}'
```

3. Mostra una pagina (numerazione da 1, salti consentiti):

```sh
curl -X POST http://127.0.0.1:8787/api/show/1
```

4. Termina. `black` lascia lo schermo nero, `logo` mostra il segnaposto della parrocchia, `off` esegue l'hook configurato per spegnere o disabilitare l'uscita:

```sh
curl -X POST http://127.0.0.1:8787/api/song/end \
  -H 'Content-Type: application/json' -d '{"idle":"black"}'
```

Stato corrente: `GET /api/state`. Il browser di proiezione si apre su `http://127.0.0.1:8787/`; premere `F` per schermo intero (o usare `--kiosk`).

## Installazione rapida sul Pi

```sh
sudo apt update
mkdir -p ~/canti-in-chiesa
```

Copiare i file sul Pi (`scp server.py projector.html pyproject.toml uv.lock pi@IP_DEL_RASPBERRY:~/canti-in-chiesa/`; per l'avvio automatico copiare anche `deploy/`), poi installare l'ambiente e avviare per prova:

```sh
cd ~/canti-in-chiesa
uv sync --locked
uv run python server.py
```

In un terminale locale sul Pi aprire Chromium in modalità kiosk:

```sh
chromium --kiosk --noerrdialogs http://127.0.0.1:8787/
```

Per l'avvio automatico, copiare i file in `deploy/` nelle posizioni indicate, sostituendo `pi` con il nome utente effettivo. Il servizio userà l'interprete dell'ambiente creato da uv (`.venv/bin/python`). Per esempio:

```sh
sudo cp ~/canti-in-chiesa/deploy/canti.service /etc/systemd/system/
mkdir -p ~/.config/autostart
cp ~/canti-in-chiesa/deploy/canti-kiosk.desktop ~/.config/autostart/
sudo systemctl daemon-reload
sudo systemctl enable --now canti.service
```

Mantieni SSH abilitato con autenticazione a chiave e disabilita login grafico locale se vuoi gestire il Pi solo da remoto. La sessione grafica kiosk deve comunque partire per pilotare il proiettore. Per il comando Chromium, alcune immagini Raspberry Pi OS usano il nome `chromium-browser`: controllare con `command -v chromium chromium-browser` e modificare il file desktop di conseguenza.

## HDMI: cosa si può controllare

Il server può eseguire gli hook `DISPLAY_ON_COMMAND` e `DISPLAY_OFF_COMMAND` quando la canzone inizia e quando termina con `idle: "off"`. Gli hook sono comandi locali amministrati sul Pi, non valori inviati dall'API. Lasciarli vuoti significa che l'API mostra/nasconde le slide ma non cambia lo stato elettrico HDMI.

Con Raspberry Pi OS moderno (driver KMS/DRM), la documentazione Raspberry Pi indica `wlr-randr` per l'uscita HDMI: per esempio `wlr-randr --output HDMI-A-1 --off` e poi `--on`. Il nome può cambiare (`HDMI-A-2` sulla seconda porta) e il comando va eseguito nella sessione Wayland; il servizio systemd di esempio gira invece fuori dalla sessione grafica, quindi un hook `wlr-randr` richiede un wrapper che raggiunga quella sessione. Il vecchio `tvservice` e `vcgencmd display_power` non sono affidabili con KMS/DRM. Le opzioni pratiche sono:

- **Schermo nero**: affidabile, uscita HDMI sempre attiva. È l'impostazione consigliata.
- **CEC**: se il proiettore supporta HDMI-CEC e il Pi vede il dispositivo CEC, inviare standby/accensione può spegnere/riaccendere il proiettore. Verificare con `cec-ctl -l` e `cec-ctl -d /dev/cec0 --playback`; supporto e sintassi dipendono dal proiettore e dal driver. Gli hook possono richiamare uno script verificato localmente.
- **Disabilitare il connettore**: possibile con `wlr-randr`, ma dipende dalla sessione grafica e dal nome output. Può interrompere il rendering/browser e va provato sull'hardware effettivo. `DISPLAY_OFF_COMMAND`/`DISPLAY_ON_COMMAND` permettono di agganciare script testati.

Per una celebrazione, consigliamo di lasciare HDMI connesso e mostrare nero tra i canti; il proiettore può andare in standby da solo quando non rileva segnale, oppure si può comandare via CEC se compatibile. L'accensione HDMI al momento della canzone dipende dal modello del proiettore e dalla sessione grafica, quindi va verificata sull'hardware effettivo; il servizio e gli hook mantengono questa parte configurabile.
