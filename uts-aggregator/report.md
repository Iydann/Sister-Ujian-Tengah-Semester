# Laporan UTS — Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

**Nama:** Abdullah Adiwarman Wildan  
**NIM:** 11231001  
**Kelas:** A  
**Mata Kuliah:** Sistem Terdistribusi dan Parallel

---

## Daftar Isi

1. [Ringkasan Sistem dan Arsitektur](#1-ringkasan-sistem-dan-arsitektur)
2. [Bagian Teori (T1–T8)](#2-bagian-teori-t1t8)
3. [Keputusan Desain Implementasi](#3-keputusan-desain-implementasi)
4. [Analisis Performa dan Metrik](#4-analisis-performa-dan-metrik)
5. [Link Pelengkap Dokumen](#6-link-pelengkap-dokumen)
6. [Daftar Pustaka](#7-daftar-pustaka)

---

## 1. Ringkasan Sistem dan Arsitektur

Mini Event Log Aggregator adalah layanan Pub-Sub berbasis FastAPI dan asyncio yang menerima event dari publisher, memrosesnya secara asinkron melalui worker consumer, dan menerapkan deduplication berbasis pasangan `(topic, event_id)` yang disimpan secara persisten di SQLite.

### Alur Data

```
Publisher
   │  POST /publish  (single atau batch event)
   ▼
FastAPI — ingestion layer
   │  asyncio.Queue  (in-memory)
   ▼
Consumer Worker — background task
   │  INSERT OR IGNORE INTO events (topic, event_id, ...)
   ▼
SQLite — dedup store (persisten via Docker volume)
   │
   ├─ GET /events?topic=...  →  event unik per topic
   └─ GET /stats             →  received, unique_processed, duplicate_dropped, topics, uptime
```

### Komponen Utama

| File | Peran |
|---|---|
| `src/main.py` | FastAPI app, startup/shutdown lifecycle, endpoint publish/events/stats |
| `src/consumer.py` | Background worker: baca queue, tentukan unique vs duplicate via dedup store |
| `src/dedup.py` | SQLite store: insert dengan UNIQUE constraint, query events per topic |
| `src/models.py` | Pydantic schema validasi event (topic, event_id, timestamp, source, payload) |
| `tests/test_app.py` | 8 unit test mencakup semua skenario rubrik |

---

## 2. Bagian Teori (T1–T8)

### T1 — Karakteristik Sistem Terdistribusi dan Trade-off Pub-Sub Aggregator
*(Bab 1 — Tanenbaum & Van Steen, 2007)*

Sistem terdistribusi adalah sekumpulan komputer independen yang tampak kepada pengguna sebagai satu sistem koheren (Tanenbaum & Van Steen, 2007, Bab 1). Karakteristik utamanya mencakup: (1) **transparansi** — pengguna tidak perlu mengetahui lokasi atau replikasi komponen; (2) **keterbukaan (openness)** — komponen dapat dipertukarkan selama mengikuti antarmuka standar; (3) **skalabilitas** — sistem tetap berfungsi ketika beban bertambah; serta (4) **fault tolerance** — kegagalan sebagian komponen tidak mematikan seluruh sistem.

Pada pola Pub-Sub log aggregator, publisher dan subscriber tidak saling mengenal secara langsung sehingga tercapai *loose coupling*. Trade-off yang umum muncul adalah: pertama, **reliabilitas vs kompleksitas** — untuk menjamin at-least-once delivery, aggregator harus menyimpan event sementara dengan overhead penyimpanan tambahan. Kedua, **throughput vs latency** — pemrosesan batch meningkatkan throughput namun mengorbankan latensi per event. Ketiga, **konsistensi vs ketersediaan (teorema CAP)** — dalam skenario partisi jaringan, kita harus memilih antara konsistensi data dan ketersediaan layanan (Tanenbaum & Van Steen, 2007, Bab 7). Pada aggregator ini dipilih ketersediaan dan konsistensi eventual, sehingga deduplication store diperlukan untuk mengoreksi duplikasi akibat at-least-once delivery.

---

### T2 — Arsitektur Client-Server vs Publish-Subscribe
*(Bab 2 — Tanenbaum & Van Steen, 2007)*

Arsitektur **client-server** bersifat sinkron dan *tightly coupled*: klien mengirim permintaan dan menunggu respons dari server yang diketahui alamatnya. Ini sederhana dan mudah di-debug, namun rapuh — jika server mati, klien gagal sepenuhnya. Sebaliknya, arsitektur **publish-subscribe** memisahkan pengirim (publisher) dari penerima (subscriber) melalui perantara topic atau broker, sehingga keduanya dapat berkembang secara independen (Tanenbaum & Van Steen, 2007, Bab 2).

Pub-Sub tepat dipilih ketika:
- Terdapat banyak publisher dan/atau subscriber yang jumlahnya dinamis.
- Pengirim tidak perlu menunggu respons pemrosesan dari penerima (asinkron).
- Dibutuhkan fan-out — satu event diterima oleh banyak consumer dengan logika berbeda.
- Sistem harus toleran terhadap kegagalan sementara; subscriber dapat membaca ulang event dari antrian.

Pada aggregator ini Pub-Sub dipilih karena publisher (pengirim log) dan consumer (prosesor log) bekerja pada kecepatan yang berbeda. Dengan `asyncio.Queue` sebagai broker sederhana, ingestion dan processing berjalan secara independen sehingga sistem tetap responsif meski consumer sedang sibuk memproses batch besar.

---

### T3 — At-Least-Once vs Exactly-Once Delivery dan Idempotent Consumer
*(Bab 3 — Tanenbaum & Van Steen, 2007)*

Semantik pengiriman pesan dalam sistem terdistribusi dibagi menjadi tiga kategori (Tanenbaum & Van Steen, 2007, Bab 3):
1. **At-most-once** — pesan mungkin hilang, tidak pernah duplikat.
2. **At-least-once** — pesan pasti terkirim, namun mungkin lebih dari sekali akibat retry.
3. **Exactly-once** — pesan terkirim tepat satu kali, namun membutuhkan koordinasi mahal (misalnya two-phase commit) yang menurunkan throughput.

Dalam praktik, exactly-once sulit dicapai tanpa trade-off besar, sehingga at-least-once menjadi pilihan umum. Konsekuensinya, consumer **wajib** bersifat **idempoten**: memproses event yang sama berkali-kali menghasilkan efek samping yang identik. Tanpa idempotency, setiap retry atau duplikat dapat menyebabkan inkonsistensi — misalnya penghitungan ganda atau pencatatan log berulang.

Pada aggregator ini, idempotency diterapkan melalui `UNIQUE constraint` pada pasangan `(topic, event_id)` di SQLite. Insert yang melanggar constraint langsung menghasilkan `IntegrityError` yang ditangkap sebagai sinyal duplikat — tanpa efek samping tambahan.

---

### T4 — Skema Penamaan Topic dan event_id
*(Bab 4 — Tanenbaum & Van Steen, 2007)*

Penamaan adalah fondasi identifikasi resource dalam sistem terdistribusi (Tanenbaum & Van Steen, 2007, Bab 4). Skema penamaan yang dirancang:

**Format topic:**
```
<domain>.<service>.<category>
Contoh: app.auth.login, app.payment.success
```

**Format event_id:**
```
<sumber>-<UUID-v4>
Contoh: srv01-550e8400-e29b-41d4-a716-446655440000
```

UUID versi 4 dipilih karena sifatnya yang *collision-resistant* secara statistik — probabilitas tabrakan dua UUID v4 yang berbeda sangat kecil sehingga praktis tidak terjadi dalam skala normal. Prefix sumber membantu traceability tanpa memerlukan koordinasi terpusat.

Dampak terhadap deduplication: dedup store menggunakan pasangan `(topic, event_id)` sebagai *composite key*, sehingga dua event dengan topic sama tetapi event_id berbeda dianggap unik, dan sebaliknya. Skema ini memungkinkan dedup yang akurat tanpa membandingkan seluruh payload event.

---

### T5 — Ordering Event: Kapan Total Ordering Tidak Diperlukan?
*(Bab 5 — Tanenbaum & Van Steen, 2007)*

Total ordering mengharuskan semua node menyetujui urutan global seluruh event — ini membutuhkan mekanisme seperti *logical clock* atau *vector clock* dengan overhead koordinasi yang signifikan (Tanenbaum & Van Steen, 2007, Bab 5).

Pada aggregator ini, **total ordering tidak diperlukan** karena:
1. Tujuan aggregator adalah pengumpulan dan deduplikasi log, bukan pengurutan transaksi bisnis yang saling bergantung.
2. Setiap event bersifat independen — urutan antara event dari topik berbeda tidak mempengaruhi korektifitas hasil.

Pendekatan praktis yang diterapkan adalah **timestamp ISO 8601 per event**. Timestamp digunakan untuk pengurutan indikatif saat query, sudah cukup untuk use case log aggregation. Keterbatasannya: clock skew antar host dapat menyebabkan pengurutan timestamp yang tidak akurat secara global, namun untuk keperluan log aggregation, *causal ordering* per sumber sudah memadai.

---

### T6 — Failure Modes dan Strategi Mitigasi
*(Bab 6 — Tanenbaum & Van Steen, 2007)*

Sistem terdistribusi menghadapi berbagai mode kegagalan (Tanenbaum & Van Steen, 2007, Bab 6). Failure modes utama pada log aggregator dan mitigasinya:

| Failure Mode | Penyebab | Strategi Mitigasi |
|---|---|---|
| Duplikasi event | Retry otomatis saat timeout | Idempotent consumer + dedup store persisten |
| Event out-of-order | Latensi jaringan bervariasi | Timestamp per-event; toleransi out-of-order di aggregator |
| Crash/restart prosesor | Kegagalan hardware/software | Dedup store di SQLite (persistent), bukan in-memory |
| Queue overflow | Consumer lambat, publisher cepat | `queue.join()` sebagai back-pressure implisit |
| Korupsi data | Penulisan parsial ke disk | SQLite dengan atomicity pada setiap `commit()` |

Untuk retry direkomendasikan strategi **exponential backoff** agar tidak membanjiri aggregator saat gangguan sementara. Dedup store yang *durable* adalah kunci: jika store hanya in-memory, restart container akan kehilangan riwayat dedup sehingga event lama bisa diproses ulang.

---

### T7 — Eventual Consistency melalui Idempotency dan Deduplication
*(Bab 7 — Tanenbaum & Van Steen, 2007)*

Eventual consistency menyatakan bahwa jika tidak ada update baru, semua replika akan konvergen ke nilai yang sama dalam waktu tertentu (Tanenbaum & Van Steen, 2007, Bab 7). Pada konteks aggregator, *eventual consistency* berarti: meskipun event yang sama mungkin tiba lebih dari sekali akibat jaringan yang tidak andal, pada akhirnya database hanya akan mencatat setiap event satu kali setelah seluruh retry selesai.

**Idempotency** dan **deduplication** berperan saling melengkapi:
- Idempotency memastikan bahwa memproses event duplikat tidak mengubah state sistem.
- Deduplication store menyediakan memori permanen tentang event mana yang sudah diproses.

Tanpa keduanya, eventual consistency tidak dapat dijamin. Kombinasi keduanya menjadikan operasi publish bersifat *idempotent secara end-to-end*: mengirim event yang sama sepuluh kali menghasilkan state yang identik dengan mengirimnya satu kali.

---

### T8 — Metrik Evaluasi Sistem
*(Bab 1–7 — Tanenbaum & Van Steen, 2007)*

| Metrik | Definisi | Target | Keputusan Desain Terkait |
|---|---|---|---|
| Throughput | Event/detik yang diproses | ≥ 500 event/s | asyncio queue; batch publish |
| Latency (P99) | Waktu dari publish ke unique_processed | < 5s untuk 120 event | Non-blocking publish; async consumer |
| Duplicate rate detection | % event duplikat yang terdeteksi | 100% (zero false negative) | UNIQUE constraint SQLite |
| Dedup accuracy setelah restart | % event lama yang dicegah setelah restart | 100% | Persistent SQLite + Docker volume mount |
| False positive rate | % event unik yang salah ditolak | 0% | UUID v4 sebagai event_id |

Metrik ini langsung terkait dengan keputusan desain yang diambil pada implementasi. Sebagai validasi: stress test `test_stress_batch_120_events_with_20_percent_duplicates` memverifikasi bahwa 120 event dengan 20% duplikasi diproses dalam batas waktu 5 detik dengan akurasi dedup 100% (Tanenbaum & Van Steen, 2007, Bab 1).

---

## 3. Keputusan Desain Implementasi

### 3.1 Idempotency dan Dedup Store

Idempotency diterapkan di level consumer, bukan publisher. Setiap event yang diambil dari queue dicoba di-insert ke tabel `events` di SQLite dengan `UNIQUE(topic, event_id)`. Jika constraint dilanggar, SQLite melempar `IntegrityError` yang ditangkap sebagai sinyal duplikat — tanpa exception yang tidak tertangani, tanpa efek samping tambahan.

Pendekatan ini lebih robust daripada cache in-memory karena:
- Persisten terhadap restart container.
- Atomik — tidak ada race condition antara "cek apakah ada" dan "insert".
- Tidak memerlukan lock eksplisit karena SQLite menangani concurrency di level database.

### 3.2 At-Least-Once Simulation

At-least-once delivery disimulasikan dengan mengirim event yang memiliki `event_id` sama lebih dari satu kali ke endpoint `/publish`. Sistem memastikan bahwa hanya satu dari event-event tersebut yang masuk ke dedup store. Ini diverifikasi oleh `test_publish_duplicate` dan `test_stress_batch_120_events_with_20_percent_duplicates`.

### 3.3 Ordering

Total ordering tidak diterapkan. Event disimpan berdasarkan urutan kedatangan di queue. Untuk keperluan log aggregation, pendekatan ini memadai karena tujuan utama adalah pengumpulan event unik, bukan rekonstruksi urutan kausal lintas sumber (lihat T5).

### 3.4 Pemilihan SQLite sebagai Dedup Store

SQLite dipilih karena:
- **Embedded** — tidak membutuhkan proses database terpisah.
- **ACID transactions** — atomicity terjamin pada setiap `commit()`.
- **Skala cukup** — ribuan hingga jutaan event untuk skala tugas ini.
- **Docker-friendly** — mudah di-mount sebagai volume agar persisten di luar lifecycle container.

### 3.5 Pseudocode Alur Utama

```
on POST /publish(events):
  normalize to list
  stats.received += len(events)
  for each event in events:
    await queue.put(event)
  await queue.join()          # tunggu sampai semua diproses
  return 202 Accepted

consumer.run():
  while true:
    event = await queue.get()
    inserted = dedup_store.insert_event(event)
    if inserted:
      stats.unique_processed += 1
      log INFO "[PROCESSED] topic={} event_id={}"
    else:
      stats.duplicate_dropped += 1
      log INFO "[DUPLICATE] topic={} event_id={}"
    queue.task_done()

dedup_store.insert_event(event):
  try:
    INSERT INTO events (topic, event_id, ...) VALUES (...)
    return True   # unique — event baru
  except IntegrityError:
    return False  # duplicate — event sudah ada
```

---

## 4. Analisis Performa dan Metrik

### Hasil Stress Test

Stress test `test_stress_batch_120_events_with_20_percent_duplicates` mengirim 120 event sekaligus dengan komposisi:
- 96 event unik (`u-0` hingga `u-95`)
- 24 event duplikat (mengirim ulang `u-0` hingga `u-23`)

Hasil yang diverifikasi:
- `received` = 120 ✓
- `unique_processed` = 96 ✓
- `duplicate_dropped` = 24 ✓
- Elapsed time < 5.0 detik ✓
- Event tersimpan di database = 96 ✓

### Hasil Unit Tests Keseluruhan

```
8 passed in 0.70s
```

Semua 8 skenario lulus, termasuk persistence setelah restart dan validasi schema.

### Kelebihan

- Dedup yang kuat berbasis constraint database — tidak mudah ditembus oleh race condition dibanding pendekatan check-then-insert.
- Sederhana dan reproducible: seluruh komponen berjalan dalam satu container tanpa dependency eksternal.
- Observability tersedia melalui endpoint `/stats` yang menampilkan `received`, `unique_processed`, `duplicate_dropped`, `topics`, dan `uptime`.

### Keterbatasan

- Antrian masih in-memory (`asyncio.Queue`): jika proses crash sebelum consumer memproses event, event dalam antrian bisa hilang.
- Benchmark formal untuk 5.000+ event dengan persentase duplikat terkontrol belum dilakukan secara eksplisit (stress test menggunakan 120 event sebagai representasi).
- Tidak ada autentikasi, rate limiting, atau distributed tracing untuk lingkungan produksi.

### Rencana Perbaikan

- Menambahkan script load test untuk mengukur throughput dan latency P99 pada 5.000+ event.
- Mengaktifkan SQLite WAL mode secara eksplisit untuk atomicity yang lebih baik pada beban tinggi.
- Menambahkan pipeline CI untuk test dan lint otomatis.

---

## 5. Link Pelengkap Dokumen

| Kebutuhan | Link |
|---|---|
| Github | https://github.com/Iydann/Sister-Ujian-Tengah-Semester |
| Video Demo | https://www.youtube.com/watch?v=Z-6tquBL5gw |

---

## 6. Daftar Pustaka

Tanenbaum, A. S., & Van Steen, M. (2007). *Distributed systems: Principles and paradigms* (2nd ed.). Prentice Hall.

FastAPI. (n.d.). *FastAPI documentation*. https://fastapi.tiangolo.com/

Kleppmann, M. (2017). *Designing data-intensive applications: The big ideas behind reliable, scalable, and maintainable systems*. O'Reilly Media.

Python Software Foundation. (n.d.). *asyncio — Asynchronous I/O*. https://docs.python.org/3/library/asyncio.html

Richardson, C. (2020, Oktober 16). *Pattern: Idempotent consumer*. Microservices.io. https://microservices.io/post/microservices/patterns/2020/10/16/idempotent-consumer.html

SQLite. (n.d.). *SQLite documentation*. https://www.sqlite.org/docs.html
