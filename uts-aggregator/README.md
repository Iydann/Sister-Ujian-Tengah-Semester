# UTS - Event Log Aggregator (Pub-Sub)

Project ini adalah implementasi mini Event Log Aggregator berbasis Pub-Sub dengan fokus pada:

- at-least-once delivery simulation,
- idempotent consumer,
- deduplication per pasangan `(topic, event_id)`,
- persistence dedup store (tetap tersimpan setelah restart),
- API observability sederhana.

Implementasi menggunakan FastAPI, consumer async berbasis queue, dan SQLite sebagai penyimpanan dedup + event.

## Fitur Utama

- `POST /publish` menerima 1 event atau batch events.
- `GET /events?topic=...` menampilkan event unik per topic.
- `GET /stats` menampilkan metrik agregator:
	- `received`
	- `unique_processed`
	- `duplicate_dropped`
	- `topics`
	- `uptime`
- Dedup store persisten di SQLite (`data/events.db` atau `DATA_DIR/events.db`).
- Duplicate di-drop otomatis berdasarkan constraint unik `(topic, event_id)`.

## Arsitektur Singkat

1. Producer mengirim event ke endpoint `/publish`.
2. Event dimasukkan ke `asyncio.Queue`.
3. `Consumer.run()` memproses event dari queue.
4. `DedupStore.insert_event()` mencoba insert ke SQLite:
	 - sukses insert -> unique event (diproses),
	 - gagal `IntegrityError` -> duplicate (di-drop).
5. Stats diperbarui untuk monitoring sederhana.

## Struktur Project

```
.
|- src/
|  |- main.py        # FastAPI app + endpoint + startup/shutdown
|  |- consumer.py    # Background consumer async
|  |- dedup.py       # SQLite dedup store + query events/topics
|  |- models.py      # Pydantic event model
|- tests/
|  |- test_app.py    # Unit/integration style tests endpoint dan dedup
|- data/
|  |- events.db      # SQLite database (persisted)
|- Dockerfile
|- docker-compose.yml
|- requirements.txt
|- README.md

```

## Event Schema
son
{
	"topic": "orders",
	"event_id": "evt-001",
	"timestamp": "2026-04-25T10:00:00",
	"source": "web",
	"payload": {
		"order_id": 123,
		"amount": 150000
	}
}
Body event yang valid:

```json
{
	"topic": "orders",
	"event_id": "evt-001",
	"timestamp": "2026-04-25T10:00:00",
	"source": "web",
	"payload": {
		"order_id": 123,
		"amount": 150000
	}
}
```

## Menjalankan Secara Lokal

### 1) Setup environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2) Run server

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8080
```

Server tersedia di:

- API: `http://localhost:8080`
- Interactive docs: `http://localhost:8080/docs`

## Contoh Penggunaan API

### Publish single event

```bash
curl -X POST "http://localhost:8080/publish" \
	-H "Content-Type: application/json" \
	-d '{
		"topic": "orders",
		"event_id": "evt-001",
		"timestamp": "2026-04-25T10:00:00",
		"source": "web",
		"payload": {"msg": "hello"}
	}'
```

### Publish batch events

```bash
curl -X POST "http://localhost:8080/publish" \
	-H "Content-Type: application/json" \
	-d '[
		{
			"topic": "orders",
			"event_id": "evt-002",
			"timestamp": "2026-04-25T10:00:01",
			"source": "web",
			"payload": {"order_id": 1}
		},
		{
			"topic": "orders",
			"event_id": "evt-002",
			"timestamp": "2026-04-25T10:00:02",
			"source": "retry-service",
			"payload": {"order_id": 1}
		}
	]'
```

### Get events by topic

```bash
curl "http://localhost:8080/events?topic=orders"
```

### Get stats

```bash
curl "http://localhost:8080/stats"
```

## Menjalankan Testing

```bash
pytest -q .
```

Cakupan test saat ini mencakup:

- publish unique event,
- duplicate detection,
- retrieval event per topic,
- request validation,
- stats consistency,
- topic-scoped dedup,
- persistence dedup setelah restart app.
- stress batch 120 event dengan ~20% duplikasi dan assert waktu eksekusi wajar.

## Menjalankan Dengan Docker

### Build image

```bash
docker build -t uts-aggregator:latest .
```

### Run container

```bash
docker run --rm -p 8080:8080 -v $(pwd)/data:/app/data uts-aggregator:latest
```

Keterangan:

- Port aplikasi: `8080`.
- Volume `-v $(pwd)/data:/app/data` memastikan database SQLite tetap persisten di host.
- Aplikasi membaca lokasi data dari env var `DATA_DIR` (default ke `data`).

## Menjalankan Dengan Docker Compose (Bonus)

Project ini juga menyertakan `docker-compose.yml` dengan 2 service lokal:

- `aggregator`: service utama FastAPI,
- `publisher`: simulator publisher yang mengirim event (termasuk duplicate) ke aggregator.

Jalankan:

```bash
docker compose up --build
```

Lalu cek endpoint dari host:

```bash
curl "http://localhost:8080/stats"
curl "http://localhost:8080/events?topic=compose"
```

## Catatan Checklist saya

- Pub-Sub style pipeline: sudah (publish -> queue -> consumer).
- Idempotent consumer + dedup `(topic, event_id)`: sudah.
- Persistence setelah restart: sudah (SQLite file).
- API wajib (`/publish`, `/events`, `/stats`): sudah.
- Unit test minimal 5: sudah (lebih dari 5 malah).
- Dockerfile: sudah dan runnable.
- Stress test kecil dengan duplikasi: sudah.
- Docker Compose bonus (2 service lokal): sudah.

## Potensi Pengembangan Lanjutan

- Mungkin bisa dengan Tambah load/performance test skala besar (misalnya 5.000 event dengan >=20% duplikat).
- Tambah endpoint healthcheck dan metrics format Prometheus.
- Tambah CI pipeline untuk lint + test otomatis.

## Author

Nama: Abdullah Adiwarman Wildan
NIM: 11231001
