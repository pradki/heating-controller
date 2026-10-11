# tests/test_feeder_logger.py - CSV z czasem pracy podajnika, blokowane między procesami
import asyncio
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fakes import check, done  # noqa: E402

from feeder_logger import FeederLogger  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


tmp_dir = Path(tempfile.mkdtemp())
path = tmp_dir / "feeder_log.csv"

logger = FeederLogger.__new__(FeederLogger)
logger.path = str(path)
logger._lock = asyncio.Lock()
if not path.exists():
    with open(path, "w", newline="") as f:
        csv.writer(f).writerow(["hour", "seconds_on"])

# --- pierwszy wpis w nowej godzinie ---
run(logger.add_seconds(27))
rows = read_rows(path)
check("nagłówek bez zmian", rows[0] == ["hour", "seconds_on"])
check("jeden wiersz z sekundami", len(rows) == 2 and rows[1][1] == "27")

# --- druga próbka w tej samej godzinie sumuje się, nie dubluje wiersza ---
hour_key = rows[1][0]
run(logger.add_seconds(13))
rows = read_rows(path)
check("wciąż jeden wiersz danych", len(rows) == 2)
check("sekundy zsumowane", rows[1] == [hour_key, "40"])

# --- ręcznie dopisany komentarz (konwencja "# add <kg> ...") przeżywa kolejne nadpisanie ---
with open(path, "a", newline="") as f:
    f.write("# add 200kg 8x25kg\n")
run(logger.add_seconds(5))
rows = read_rows(path)
check("komentarz nie zniknął przy kolejnym add_seconds",
      any(r and r[0].startswith("# add 200kg") for r in rows))
check("a licznik tej samej godziny dalej się sumuje",
      [r for r in rows if r and r[0] == hour_key][0][1] == "45")

done()
