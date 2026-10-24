# Servio — AI Service Agents

Servio เป็นระบบผู้ช่วยบริการลูกค้าผ่าน Web Chat และเสียง ใช้ FastAPI, OpenAI Agents SDK, Next.js และ PostgreSQL พร้อม pgvector จัดการ Team Agents, Integrations, Local Knowledge และช่องทางสนทนาผ่านหน้า Admin

## ความสามารถปัจจุบัน

- **Team Workflow**: สร้าง Agent บน Canvas กำหนด Provider, Model ID, Tools, Knowledge และ Handoffs พร้อม Private chat สำหรับทดลองทีมและ Agent
- **LLM Providers**: เชื่อมต่อผู้ให้บริการที่รองรับ OpenAI-compatible API เพิ่ม Model ID และกำหนดโมเดลสำหรับ OCR และ Image Q&A
- **Local Knowledge**: นำเข้าเอกสาร ข้อความ หลาย URL รูปภาพ และเสียง จัดการสิทธิ์ตามทีม แก้ไขแหล่งข้อมูลและนำเข้าใหม่ได้
- **Hybrid Search**: รวม Semantic Search และ Keyword Search ด้วย Reciprocal Rank Fusion (RRF) บน PostgreSQL และ pgvector
- **Web Chat**: แสดงคำตอบพร้อมภาพและเสียงอ้างอิง รองรับแนบภาพพร้อมข้อความเพื่อค้นหาสินค้า และแสดง Carousel พร้อมปุ่มดูรายละเอียดและสอบถามสินค้านี้
- **Integrations**: Custom API พร้อมแปลง cURL เป็นช่องกรอกข้อมูล และ MCP รวมถึงผลลัพธ์สินค้าแบบ `structuredContent`
- **Channels**: สร้าง Web Chat และโค้ด Widget สำหรับเว็บไซต์ พร้อมการสนทนาแบบข้อความและเสียง

Local Knowledge เป็นระบบหลัก ส่วน Gemini Document Search เป็น Legacy และปิดการสร้างใหม่เป็นค่าเริ่มต้น

## เริ่มติดตั้งด้วย Docker

ต้องมี Git, Docker Engine และ Docker Compose ส่วน Embedding, Vision และ Audio Processor เป็นบริการแยกที่ต้องจัดเตรียมเมื่อเปิดฟีเจอร์นั้น

```sh
git clone https://github.com/rujirapongsn2/servio.git
cd servio
./services.sh install
```

ตัวติดตั้งรองรับ Linux เป็นหลัก ช่วยตั้งค่า `.env`, โดเมน, พอร์ต, ใบรับรอง และเริ่มบริการ ดูตัวเลือกด้วย `./services.sh help`

สำหรับติดตั้งจากค่าที่เตรียมไว้ ให้คัดลอกไฟล์ตัวอย่างเฉพาะเครื่องใหม่:

```sh
cp .env.example .env
openssl rand -hex 32
```

ใส่ค่าที่สร้างใน `JWT_SECRET_KEY` แล้วกำหนด API key, รหัสผ่านฐานข้อมูล, `ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL` และ `NEXT_PUBLIC_WEBSOCKET_ENDPOINT` ให้ตรงกับระบบ ก่อนรันตัวติดตั้ง อย่าคัดลอกทับ `.env` ของระบบที่ใช้งานอยู่

เมื่อใช้พอร์ตค่าเริ่มต้นของ Compose:

| ส่วน | URL |
| --- | --- |
| Frontend | `https://localhost` |
| Admin | `https://localhost/admin` |
| Backend health | `https://localhost/api/health` |
| WebSocket | `wss://localhost/ws` |

หากใช้โดเมนหรือพอร์ตอื่น ให้เปลี่ยน URL ตามค่าที่ตั้งไว้ ใบรับรองที่สร้างสำหรับเครื่อง local เป็น self-signed สำหรับเว็บไซต์จริงให้ใช้ HTTPS ที่เบราว์เซอร์เชื่อถือ

### โครงสร้างบริการ

| บริการ | หน้าที่ |
| --- | --- |
| nginx | Reverse proxy ไปยัง Frontend, API และ WebSocket |
| frontend | Next.js บนพอร์ต 3000 ภายใน container |
| backend | FastAPI บนพอร์ต 8000 ภายใน container |
| postgres | `pgvector/pgvector:pg15` เก็บข้อมูลใน volume `postgres_data` |
| Embedding service | บริการภายนอก Compose สำหรับสร้าง Vector ขนาด 768 มิติ |
| Audio Processor | บริการภายนอก Compose สำหรับตรวจ เตรียม และถอดเสียง |

Compose ไม่เริ่ม Embedding, Whisper หรือ Vision Model ให้อัตโนมัติ สำหรับ Mac mini ที่รัน Backend และ Frontend แบบ native ให้ใช้ตัวจัดการ process ของเครื่องนั้น แทนการเริ่ม Docker stack ซ้ำ

## ตั้งค่าโมเดลและ Local Knowledge

เริ่มจาก [.env.example](.env.example) และ [คู่มือตั้งค่าโมเดล](docs/model-configuration.md) ค่า Model ID ต้องตรงกับบริการที่เรียกจริง การระบุชื่อโมเดลไม่ได้ทำให้ Provider รองรับภาพ เสียง หรือ Tool Calls เพิ่มขึ้นเอง

Agent ที่ใช้ Default OpenAI ใช้เส้นทาง Responses API ส่วน Custom Provider ใช้ Chat Completions ตั้งค่า Provider และ Model ให้ตรงกับความสามารถของปลายทาง

### Embedding ข้อความ รูปภาพ และเสียง

ไฟล์ตัวอย่างตั้งค่าทั้งสามประเภทไปยังบริการร่วมบนพอร์ต 8090:

```dotenv
EMBEDDING_BASE_URL=http://host.docker.internal:8090/v1
EMBEDDING_MODEL=ggml-org/embeddinggemma-2-GGUF:BF16
MULTIMODAL_EMBEDDING_BASE_URL=http://host.docker.internal:8090/v1
MULTIMODAL_EMBEDDING_MODEL=ggml-org/embeddinggemma-2-GGUF:BF16
AUDIO_EMBEDDING_BASE_URL=http://host.docker.internal:8090/v1
AUDIO_EMBEDDING_MODEL=ggml-org/embeddinggemma-2-GGUF:BF16
```

ต้องมีบริการที่รองรับชนิดข้อมูลนั้นและส่ง Vector 768 มิติกลับมา หากรัน Python แบบ native บนเครื่องเดียวกัน ให้เปลี่ยน `host.docker.internal` เป็น `127.0.0.1` หากใช้ Linux Docker ให้ตรวจว่าชื่อนี้ resolve ไปยัง host ได้

หาก Embedding Service ต้องใช้ API key ให้ตั้งคีย์แยกตามบริการ:

```dotenv
EMBEDDING_API_KEY=
MULTIMODAL_EMBEDDING_API_KEY=
AUDIO_EMBEDDING_API_KEY=
```

คีย์ที่ไม่ว่างจะถูกส่งเป็น `Authorization: Bearer …` ทั้งการสร้าง Vector และค้นหา โดย Health Check ภาพและเสียงใช้คีย์ของบริการนั้นกับ `/health` และ `/props` ด้วย คีย์เหล่านี้ไม่ถูกส่งไปยัง Audio Processor และไม่ใช้ `OPENAI_API_KEY` แทน หากบริการไม่ต้องยืนยันตัวตนให้เว้นว่าง การเปลี่ยนคีย์ไม่ต้อง Re-index แต่ต้องรีสตาร์ต Backend เพื่อรับค่าใหม่

เปิดเฉพาะฟีเจอร์ที่บริการพร้อม:

```dotenv
LOCAL_KNOWLEDGE_HYBRID_ENABLED=true
LOCAL_KNOWLEDGE_IMAGES_ENABLED=true
LOCAL_KNOWLEDGE_AUDIO_ENABLED=true
```

ค่าเหล่านี้เป็น `false` ในไฟล์ตัวอย่าง ก่อนเปิดเสียง ให้ระบุ `AUDIO_EMBEDDING_REVISION` ตาม revision ของ weights และ projector ที่ใช้งานจริง สำหรับภาพให้กำหนด `MULTIMODAL_EMBEDDING_SPACE` ให้ตรงกับชุดโมเดล เมื่อเปลี่ยนโมเดลหรือ Vector space ต้อง Re-index ข้อมูลประเภทนั้น

### รูปภาพและ OCR

รองรับ JPG และ PNG พร้อมเก็บภาพต้นฉบับ OCR ใช้ Vision Model แยกจาก Embedding ตั้งโมเดลใน **Settings → Providers** แล้วเลือกโมเดลเริ่มต้นสำหรับ OCR และ Image Q&A

```dotenv
IMAGE_OCR_MODEL_SOURCE=database
IMAGE_QA_MODEL_SOURCE=database
LOCAL_KNOWLEDGE_IMAGE_OCR_ENABLED=true
LOCAL_KNOWLEDGE_IMAGE_QA_ENABLED=true
```

หากต้องการตั้งโมเดลผ่าน `.env` ให้ใช้ source `environment` และระบุ Model, Base URL และ API Key ของแต่ละงานให้ครบ ดู [OCR](docs/local-knowledge-ocr.md), [Image Knowledge](docs/local-knowledge-images.md) และ [การค้นหาสินค้าจากภาพ](docs/image-product-matching.md)

### เสียง: Local Whisper หรือ Groq

`AUDIO_PROCESSOR_BASE_URL` ชี้ไปยัง **Servio Audio Processor** ซึ่งให้ API `/health`, `/preview`, `/extract` และ `/normalize` จึงไม่สามารถเปลี่ยนค่านี้เป็น Groq โดยตรง

Local Whisper เป็นค่าเริ่มต้น:

```dotenv
AUDIO_PROCESSOR_BASE_URL=http://host.docker.internal:8094
KNOWLEDGE_AUDIO_ASR_PROVIDER=local
KNOWLEDGE_AUDIO_WHISPER_CLI=/absolute/path/to/whisper-cli
KNOWLEDGE_AUDIO_WHISPER_MODEL=/absolute/path/to/whisper-model.bin
KNOWLEDGE_AUDIO_VAD_MODEL=/absolute/path/to/silero-vad.bin
KNOWLEDGE_AUDIO_ASR_REVISION=your-pinned-whisper-and-vad-revisions
KNOWLEDGE_AUDIO_USE_GPU=false
```

ติดตั้ง `ffmpeg`, `ffprobe`, whisper.cpp และโมเดลก่อนเริ่ม Processor:

```sh
./scripts/run_audio_processor.sh
curl --fail http://127.0.0.1:8094/health
```

คำสั่งนี้ bind ที่ `127.0.0.1` สำหรับ Backend แบบ native หาก Backend อยู่ใน Linux Docker ให้ export `KNOWLEDGE_AUDIO_BIND` เป็น IP ของ host interface ที่ Docker เข้าถึงได้ก่อนเริ่มสคริปต์ และจำกัดการเข้าถึงพอร์ต 8094 ให้เฉพาะเครือข่ายที่เชื่อถือ การตั้ง Bind ไว้เฉพาะใน `.env` ไม่มีผลต่อ shell launcher ตรวจทั้งชื่อ `host.docker.internal` และการเชื่อมต่อจาก container จริง

Health ต้องแสดง `ready: true` หากใช้ Apple Silicon พร้อม whisper.cpp ที่ build รองรับ Metal สามารถตั้ง `KNOWLEDGE_AUDIO_USE_GPU=true` ได้

หากต้องการถอดเสียงผ่าน Groq ให้เปลี่ยนเฉพาะ Provider และกำหนดคีย์:

```dotenv
KNOWLEDGE_AUDIO_ASR_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
KNOWLEDGE_AUDIO_GROQ_MODEL=whisper-large-v3-turbo
```

Groq รับเสียง WAV ที่ normalize แล้วเพื่อถอดเสียง การ Preview, Normalize และสร้าง Embedding ยังใช้บริการเดิม ไม่มีการสลับผู้ให้บริการอัตโนมัติเมื่อเกิดข้อผิดพลาด ข้อมูลที่นำเข้าไว้แล้วจะยังค้นหาได้

Processor อ่านเฉพาะ `KNOWLEDGE_AUDIO_*` และ `GROQ_API_KEY` จาก `.env` ส่วนค่าที่กำหนดไว้ใน environment ของ process มีลำดับความสำคัญสูงกว่า ต้องรีสตาร์ต Processor หลังแก้ค่าเหล่านี้ การรีสตาร์ต Backend อย่างเดียวไม่เปลี่ยนค่า Processor

บน Mac mini ที่ติดตั้ง LaunchAgent `ai.softnix.servio.audio-processor` ไว้แล้ว:

```sh
launchctl kickstart -k gui/$(id -u)/ai.softnix.servio.audio-processor
```

ใช้ **Reindex** เพื่อถอดเสียงจากต้นฉบับใหม่ด้วย Provider ปัจจุบัน ส่วน **Reindex vectors** ใช้บทถอดเสียงที่เก็บไว้ ดู [คู่มือ Audio Knowledge](docs/local-knowledge-audio.md) สำหรับการติดตั้งและตรวจสอบบริการ

### ขนาดไฟล์และความพร้อม

| ประเภท | รองรับ | ขีดจำกัด |
| --- | --- | --- |
| เอกสาร | PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, JSON, HTML และ archives | รวมไฟล์อัปโหลดไม่เกิน 50 MB ต่อครั้ง |
| รูปภาพ | JPG, PNG | ไม่เกิน 10 MB ต่อภาพ และอยู่ภายใต้ขีดจำกัดรวม |
| เสียง | WAV, MP3 | ไม่เกิน 50 MB และสูงสุด 10 นาทีต่อไฟล์ |

หน้า **Add Knowledge** ตรวจความพร้อมของบริการ หาก Audio แสดง Unavailable ให้ตรวจ `/health` ของ Audio Processor และบริการ Audio Embedding การตั้งคีย์ Groq อย่างเดียวไม่เปิดฟีเจอร์เสียง

## สร้างทีมและเริ่มสนทนา

1. เปิด **Team Agents** แล้วสร้างหรือเลือกทีม
2. เข้า **Workflow** เพิ่ม Agent ผ่านปุ่มบน Canvas หรือ **+ Agent** แล้วเลือก Provider, Model และ Instructions
3. เพิ่ม Tools และ Knowledge ให้ Agent กำหนด Handoffs และบันทึก
4. ใช้ **Private chat** ทดลองทีม หรือปุ่ม **Chat** ของ Agent เพื่อทดลองเฉพาะตัว
5. เปิด **Channels** ภายใน Workflow เพื่อเลือก Web Chat เดิมหรือสร้างช่องทางสำหรับผู้ใช้

Private chat ใช้สำหรับทดลองและไม่สร้าง Channel ให้เอง Tools บางประเภท เช่น Custom API และ MCP ไม่พร้อมใช้ใน Preview ให้ทดสอบผ่าน Channel เมื่อเชื่อมระบบเหล่านี้

ใน **Add Knowledge** เลือก Files, Paste Text หรือ URLs สำหรับหลาย URL สามารถแก้ไขและนำเข้าใหม่แยกราย URL ได้ ทดสอบคำถามและตรวจต้นฉบับในหน้ารายละเอียด Knowledge ก่อนให้ Agent ใช้งาน ดู [คู่มือ URL Knowledge](docs/local-knowledge-urls.md)

## เชื่อม API, MCP และ Widget

Custom API รองรับวาง cURL เพื่อเติม Method, URL, Headers, Query และ Body โดยไม่รันคำสั่งนั้น ดู [คู่มือ Custom API](docs/custom-api-integrations.md)

Carousel สินค้ารับข้อมูลตาม schema ที่กำหนดจาก Custom API หรือ MCP `structuredContent` มีข้อความสรุป ภาพ และปุ่ม **ดูรายละเอียด** และ **สอบถามสินค้านี้** ดู [รูปแบบ Product Carousel](docs/web-product-carousel.md)

สร้าง Widget จาก Channel แล้วใช้โค้ดที่ระบบสร้างให้ โค้ดมีค่าของช่องทางและการตั้งค่าการเข้าถึง จึงควรใช้โค้ดที่คัดลอกจากระบบแทนตัวอย่างที่ไม่มี Channel API key ตั้ง Allowed domains และ URL ให้ตรงกับเว็บไซต์ที่จะติดตั้ง

## ดูแลและอัปเดตระบบ

คำสั่งต่อไปนี้ใช้กับ Docker deployment:

```sh
./services.sh status
./services.sh logs backend
./services.sh restart backend
./services.sh rebuild backend
./services.sh rebuild frontend
./services.sh update
```

- แก้ Python หรือ dependency: Rebuild Backend
- แก้ Frontend หรือ `NEXT_PUBLIC_*`: Rebuild Frontend
- แก้ `.env` ฝั่ง Backend: `./services.sh restart backend` เพื่อ recreate container พร้อมค่าใหม่
- แก้ค่าของ Audio Processor: รีสตาร์ต Processor แยกต่างหาก

ฐานข้อมูลเก็บใน `postgres_data` ส่วนไฟล์ Knowledge เก็บภายใต้ `server/data` ตาม volume ใน Compose สำรองทั้งสองส่วนก่อนอัปเดตระบบจริง อย่าลบ volume เมื่อต้องการเพียงอัปเดตโค้ด

## พัฒนาและทดสอบ

สำหรับรันแบบ native ต้องมี Node.js 20+, Python 3.11+, `uv` และ PostgreSQL พร้อม pgvector ตั้ง `DATABASE_URL` และ endpoint ของบริการให้เข้าถึงได้จาก process ที่รันจริง

```sh
make sync
cd frontend
npm run dev
```

`npm run dev` เริ่มทั้ง Next.js และ Backend สำหรับรันแยก ใช้ `npm run dev:next` ใน `frontend` และ `uv run server.py` ใน `server` ตั้งค่า Frontend API และ WebSocket ให้ตรงกับพอร์ตที่แสดงตอนเริ่มบริการ

รัน Backend tests จาก `server`:

```sh
uv run pytest tests/test_audio_processor.py tests/test_audio_processor_groq.py tests/test_knowledge_audio.py tests/test_knowledge_images.py tests/test_local_rag.py tests/test_local_rag_coverage.py -q
```

ชุดทดสอบ timeout ของ Groq ใช้ HTTP server บน loopback และต้องเปิดพอร์ต local ได้ การทดสอบ API จำลองไม่ใช้ Groq key จริง สำหรับการยืนยัน Provider จริง ให้ใช้เสียงตัวอย่างที่อนุญาตให้ส่งไปยัง Provider และฐานข้อมูลทดสอบแยก

รัน Frontend checks จาก `frontend`:

```sh
npm run test:regression
npx tsc --noEmit --incremental false
npm run build
```

ดู [Workflow deployment](docs/workflow-deployment.md) สำหรับตรวจ artifact และ public URL ก่อนนำ release ไปใช้

## คู่มือเพิ่มเติม

- [โมเดลและ Provider](docs/model-configuration.md)
- [Local Knowledge และ pgvector](docs/LOCAL_KNOWLEDGE_PGVECTOR.md)
- [ขอบเขต Legacy Gemini](docs/LOCAL_KNOWLEDGE_NO_GEMINI_MIGRATION.md)
- [รูปภาพและ OCR](docs/local-knowledge-ocr.md)
- [เสียงและ Audio Processor](docs/local-knowledge-audio.md)
- [URL Knowledge](docs/local-knowledge-urls.md)
- [Product Carousel](docs/web-product-carousel.md)

## Contributing และ License

ส่ง Issues และ Pull Requests พร้อมขอบเขตการเปลี่ยนแปลงและผลทดสอบ โปรเจกต์ใช้ [MIT License](LICENSE)
