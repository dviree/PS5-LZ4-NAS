# ps5-lz4: LZ4 HC-packning av PS5-spel på NAS:en

All extraktion, LZ4-komprimering, verifiering och filhantering sker i en
Docker-container på NAS:en. Inget körs på PS5:an eller Macen.

- **Riktig LZ4 HC**, nivå 9 som standard: projektets egen packare
  (`ampr_pack_cli`, samma C-kod som PS5-appen 1.4.2). Ingen zlib/PFSC.
- **APR-EMU PackedStdio-runtime** (SHA-256 `69e6c4d5…`) läggs i
  `fakelib/libSceAmpr.sprx`.
- **Originalen rörs aldrig**: biblioteket monteras skrivskyddat (`:ro`) i
  containern, och verktyget raderar bara i sin egen arbetsmapp.
- **Containern har inget nätverk** (`network_mode: none`) och ändrar inga
  andra containrar eller NAS-inställningar.

## Installation

Som root på NAS:en (`sudo -i`):

```sh
mkdir -p /volume2/docker/ps5-lz4 && cd /volume2/docker/ps5-lz4
curl -L https://github.com/dviree/PS5-LZ4-NAS/archive/refs/heads/nas-build.tar.gz | tar xz
mv PS5-LZ4-NAS-nas-build src

# 1. Kontrollera bara: arkitektur, Docker, kataloger, ledigt utrymme,
#    befintliga filer och containrar. Ändrar ingenting.
bash src/nas-lz4/install.sh --check

# 2. Installera (bygget tar några minuter, därför nohup)
nohup bash src/nas-lz4/install.sh > install.log 2>&1 &
tail -f install.log
```

Installationen:

- skapar `docker-compose.yml`, `.env`, `lz4-ps5.sh`, `logs/`, `reports/` och
  `state/` i `/volume2/docker/ps5-lz4/`;
- bygger imagen `ps5-lz4:local` (logg: `logs/build.log`);
- startar containern `ps5-lz4`;
- kör en självkontroll (`doctor`) och listar biblioteket.

Filer från ett tidigare skript (`Dockerfile`, `lz4-ps5.sh` m.fl.)
säkerhetskopieras till `backup-<tid>/` och skrivs inte över utan backup. En
gammal `/volume1/games/ps5-lz4/.work/` lämnas orörd; verktyget använder
`.ps5lz4-work/`.

Standardvärden går att ändra med miljövariabler, t.ex.
`NAS_USER=nasuser LIBRARY=/volume1/games/roms/ps5 OUTPUT=/volume1/games/ps5-lz4 bash src/nas-lz4/install.sh`.

## Kommandon

Kör från `/volume2/docker/ps5-lz4/` med `sudo` (Docker kräver root). Jobben
körs inne i containern som din användare, så filerna ägs av `nasuser`.

| Kommando | Vad det gör |
| --- | --- |
| `./lz4-ps5.sh scan --check` | Listar biblioteket med nummer, status och om spelet kan använda LZ4 (läser `eboot.bin` direkt ur `.exfat` utan extraktion) |
| `./lz4-ps5.sh start 3` | Startar spel nr 3 i bakgrunden (nohup). Flera spel blir en kö: `start 3 5 "Mitt spel.exfat" PPSA12345` |
| `./lz4-ps5.sh start --all` | Alla spel som inte är klara |
| `./lz4-ps5.sh run 3` | Samma som `start`, men i förgrunden |
| `./lz4-ps5.sh status` | Pågående jobb, steg och förlopp, kö och fel |
| `./lz4-ps5.sh stop` | Stoppar jobbet; arbetet sparas |
| `./lz4-ps5.sh start --resume` | Fortsätter en stoppad/avbruten kö efter senast klara steg |
| `./lz4-ps5.sh report` | Originalstorlek, LZ4-storlek och besparing per spel och totalt |
| `./lz4-ps5.sh verify "Mitt spel-lz4"` | Verifierar ett färdigt resultat igen (alla block avkodas, CRC) |
| `./lz4-ps5.sh clean <namn>` | Tar bort arbetsmappen för ett misslyckat spel |
| `./lz4-ps5.sh doctor` | Självkontroll |

Alternativ till `start`/`run`: `--level N` (1–4 LZ4 fast, 5–12 LZ4 HC,
standard 9), `--require-vhash` (hoppa över `.ffpfsc` utan `.vhash`) och
`--force-image` (packa en image även om samma spel finns som mapp).

**Testa ett spel först:** `scan --check`, sedan `start <nr>` för ett
kompatibelt spel, sedan `status` och `report`. Kontrollera det på PS5:an
innan du kör `start --all`.

## Vad som händer med varje spel

1. **Källa**
   - **Spelmapp:** används direkt (skrivskyddad), ingen extraktion.
   - **`.exfat`:** extraheras med MkPFS 1.1.0:s exFAT-läsare (ingen mount,
     ingen privilegierad container). Varje fil kontrolleras mot imagens
     katalog: att den finns och har rätt storlek.
   - **`.ffpfs` / `.ffpfsc`:** först packas den yttre PFS-imagen upp, sedan
     den inre (`pfs_image.dat` eller `.exfat`). Om `<image>.vhash` finns
     (skrivs av PS5-appen/Game Compressor) kontrolleras varje 64 KiB-block i
     den inre imagen mot dess SHA-256. Avvikelse = jobbet stoppas.
   - Finns samma spel (samma Title ID) både som mapp och som image används
     mappen och imagen hoppas över.
2. **Kompatibilitet** (samma regel som PS5-appen): spelet måste importera
   `libSceAmpr` i `eboot.bin` eller `sce_module/*.prx`, eller redan ha
   APR-EMU i `fakelib/`. Annars hoppas det över. Redan LZ4-packade spel och
   spel där LZ4 inte kan krympa något hoppas också över.
3. **Packning:** LZ4 HC på alla kärnor utom en (N100: 3 workers), med
   lägre prioritet (`nice`/`ionice`) så att andra tjänster inte svälts.
   Profilen väljs automatiskt: en egen TOML i
   `state/profiles/<TITLEID>.toml`, annars en medföljande profil (ASTRO BOT,
   UFC 6, Insomniac, Unity), annars den skanningsbaserade. Packaren jämför
   varje packad fil byte för byte med källan.
4. **Verifiering:**
   - `ampr_pack_cli verify` kontrollerar manifest och CRC, avkodar varje
     chunk och jämför igen byte för byte med källan.
   - Formatet kontrolleras: `AMPRPAK4`-index, `AMPRDAT3`-volymer, sidecars
     och att runtime-filen är exakt den fastlåsta PackedStdio-versionen.
5. **Återställningstest:** allt packas upp till en temporär mapp och varje
   fil jämförs byte för byte med källan. Bara `ampr_emu.index` och
   `fakelib/libSceAmpr.sprx` får skilja sig (de läggs till eller byts ut
   avsiktligt).
6. **Publicering:** resultatet flyttas till
   `/volume1/games/ps5-lz4/<namn>-lz4/`. Rapporten skrivs till
   `reports/<namn>.json` och `summary.tsv`. Arbetsmappen (extraktion,
   verktygsloggar) raderas. En kort logg per spel finns kvar i
   `logs/<namn>.log`.

Misslyckas något steg behålls arbetsmappen i
`/volume1/games/ps5-lz4/.ps5lz4-work/<namn>/` för felsökning (`status` visar
felet). Kör samma spel igen så fortsätter det efter senast klara steg.
Ett steg som avbröts mitt i görs om från början. Ett befintligt resultat
skrivs aldrig över.

Utrymme: allt stort hamnar på `/volume1`. Räkna med ungefär 3× spelets
uppackade storlek ledigt under jobbet (extraktion + packar +
återställningstest); verktyget kontrollerar det före varje steg och
behåller 20 GB marginal.

## Verifierat på NAS:en ≠ spelbart på PS5

`verified_on_nas: true` i rapporten betyder att LZ4-paketen är korrekta: varje
fil kommer tillbaka byte för byte. Det betyder **inte** att spelet är testat
på konsolen (`playable_on_ps5: not tested`). Att spela kräver:

- **Ett annat format än `.ffpfsc`.** Resultatet är en vanlig spelmapp med
  `ampr_assets.index`, `.pak`-volymer, sidecars, `ampr_emu.index` och
  `fakelib/libSceAmpr.sprx`.
- **Rätt runtime.** Paketen kan bara läsas av APR-EMU PackedStdio-runtime
  (0.4.2.1), som ligger i mappen. Byt den inte mot en annan APR-EMU-version.
- **ShadowMountPlus** som laddar `fakelib/libSceAmpr.sprx` i stället för
  systemmodulen. Kopiera mappen till konsolen, t.ex. `/data/homebrew/` eller
  en extern disk, så tar ShadowMountPlus upp den. Uppströmsprojektet är
  testat på firmware 13.60 med ShadowMountPlus 1.7.
- **Rätt profil.** Resultatet varierar mellan spel. Uppströms säger att en
  trace-baserad profil är säkrare än den automatiska; lägg en sådan TOML i
  `state/profiles/<TITLEID>.toml`.
- **Behåll originalet tills spelet har startats.** Uppströms har LZ4 från
  `.ffpfsc`-källor ännu inte testats på konsol.

## Filer

```
/volume2/docker/ps5-lz4/
  src/                  källkod (det här repot)
  docker-compose.yml    .env    lz4-ps5.sh
  logs/                 build.log, <spel>.log, queue-*.log
  reports/              <spel>.json, <spel>.skipped.json, summary.tsv
  state/                kö, lås, egna profiler (state/profiles/)
/volume1/games/ps5-lz4/
  <spel>-lz4/           färdiga LZ4-spel
  .ps5lz4-work/         arbetsmappar (tomma efter lyckade jobb)
```
