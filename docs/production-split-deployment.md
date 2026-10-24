# ติดตั้ง Production โดยแยก Servio กับ Embedding Service

คู่มือนี้ติดตั้ง **Host A: Servio** และ **Host B: Embedding** บน Linux โดยใช้เครือข่ายภายใน เครื่อง A รัน Servio ด้วย Docker Compose ส่วนเครื่อง B รัน inference ด้วย systemd และใช้ Nginx ตรวจ Bearer API key ผ่าน HTTPS

ค่าตัวอย่างต้องเปลี่ยนให้ตรงกับเครื่องจริง:

| รายการ | Host A | Host B |
| --- | --- | --- |
| Private IP | `10.20.0.10` | `10.20.0.20` |
| DNS | `servio.example.com` | `embedding.internal.example` |
| บริการ | Servio, PostgreSQL/pgvector, Audio Processor เมื่อใช้เสียง | EmbeddingGemma 2 พร้อม projector, Nginx |
| พอร์ตที่รับจากอีกเครื่อง | ไม่มีพอร์ตฐานข้อมูลหรือ Backend ที่ต้องเปิดให้ B | TCP 443 จาก A เท่านั้น |
| พอร์ต inference | — | `127.0.0.1:8090` ไม่เปิดออกเครือข่าย |

เส้นทางข้อมูล: `Servio Backend → HTTPS:443 + Bearer key → Nginx → HTTP:8090 → Embedding model` ฐานข้อมูลและไฟล์ Knowledge อยู่บน A การแยกเครื่องไม่ได้ย้ายฐานข้อมูลไป B แต่ข้อความ รูปภาพ และช่วงเสียงที่ต้องสร้าง Vector จะถูกส่งไป B

## 1. เตรียมเครื่องและเครือข่าย

บน A ติดตั้ง Git, Docker Engine และ Docker Compose ใช้ DNS และใบรับรอง HTTPS ของโดเมน Servio ตามระบบที่จะเผยแพร่

บน B เตรียม Nginx, Python 3, OpenSSL, binary `llama-server` ที่รองรับ EmbeddingGemma 2 ทั้งภาพและเสียง และ GPU runtime ตามฮาร์ดแวร์ เลือก RAM/VRAM จากขนาดโมเดลและโหลดที่ทดสอบจริง คู่มือนี้ไม่ได้กำหนดจำนวนผู้ใช้พร้อมกันที่รับประกันได้

ตั้ง DNS ให้ A รวมถึง Backend container resolve `embedding.internal.example` เป็น `10.20.0.20` เปิด Firewall ของ B เฉพาะ TCP 443 จาก IP ขาออกจริงของ A หากมี NAT ให้ใช้ IP ที่ B มองเห็น ไม่เปิด 8090, PostgreSQL หรือ Audio Processor ต่ออินเทอร์เน็ต

ใช้ certificate ที่ครอบคลุม `embedding.internal.example` และมี chain ที่ Backend เชื่อถือ หากใช้ Internal CA ให้ mount CA เข้า container และตั้ง `SSL_CERT_FILE` ตามขั้นตอนที่ 4 อย่าปิดการตรวจ TLS

## 2. เตรียมโมเดลบน Host B

จัดเตรียม binary ที่ `/opt/llama/bin/llama-server` จาก build ที่ผ่านการทดสอบ แล้วบันทึก commit ของ binary ไว้กับ release ติดตั้ง weights และ projector ที่เข้าคู่กันไว้ใน `/srv/embedding`

ตัวอย่างชุด BF16 ที่โครงการใช้คือ `embeddinggemma-2-BF16.gguf` และ `mmproj-embeddinggemma-2-BF16.gguf` จาก [ggml-org/embeddinggemma-2-GGUF](https://huggingface.co/ggml-org/embeddinggemma-2-GGUF) ใช้ revision เดียวกันและบันทึก SHA256 ของทั้งสองไฟล์:

```sh
sha256sum /srv/embedding/embeddinggemma-2-BF16.gguf /srv/embedding/mmproj-embeddinggemma-2-BF16.gguf
/opt/llama/bin/llama-server --version
```

การมีชื่อ EmbeddingGemma 2 หรือ API แบบ OpenAI-compatible ไม่รับประกันว่าจะรองรับภาพและเสียงตามรูปแบบ Servio ต้องผ่านการทดสอบในขั้นตอนที่ 5 ก่อนเปิดใช้งาน ดู options ของ build ที่ติดตั้งด้วย `--help` และ [เอกสาร llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

สร้างผู้ใช้ระบบ `servio-embedding` และให้สิทธิ์อ่าน binary กับไฟล์โมเดล จากนั้นคัดลอก [embedding-host.env.example](examples/embedding-host.env.example) ไปที่ `/etc/servio-embedding/embedding.env` ปรับ path และ GPU layers ให้ตรงกับเครื่อง ตั้งเจ้าของเป็น root และ permission `0640` โดยให้กลุ่มของ service อ่านได้

สร้าง `/etc/systemd/system/servio-embedding.service`:

```ini
[Unit]
Description=Servio embedding inference
After=network.target

[Service]
Type=simple
User=servio-embedding
Group=servio-embedding
EnvironmentFile=/etc/servio-embedding/embedding.env
ExecStart=/opt/llama/bin/llama-server --model ${EMBEDDING_MODEL_PATH} --mmproj ${EMBEDDING_PROJECTOR_PATH} --alias ${EMBEDDING_ALIAS} --embeddings --host 127.0.0.1 --port 8090 --n-gpu-layers ${EMBEDDING_GPU_LAYERS} --ctx-size 8192 --batch-size 2048 --ubatch-size 2048 --parallel 1 --no-webui
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

ตัวอย่างใช้ GPU layers 99 ต้องใช้ binary ที่ build รองรับ GPU ของเครื่อง หากใช้ CPU ให้เลือก build ที่เหมาะสมและตั้ง GPU layers เป็น 0 ตั้งค่าเพิ่มเติมตามผลทดสอบหน่วยความจำและ driver ของเครื่องนั้น

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now servio-embedding
curl --fail http://127.0.0.1:8090/health
curl --fail http://127.0.0.1:8090/props
```

`/health` ต้องรายงาน `status` เป็น `ok`, `ready` หรือ `healthy` ส่วน `/props` ต้องมี `modalities.vision=true` และ `modalities.audio=true` เมื่อจะใช้ครบสามประเภท หาก build ตอบรูปแบบอื่น หยุดและแก้ compatibility ก่อน ไม่เปลี่ยน health ให้รายงานพร้อมทั้งที่ inference ยังไม่รองรับ

## 3. ตั้ง HTTPS gateway และ API key บน Host B

ตัวอย่างนี้ใช้ **คีย์เดียวที่ gateway** สำหรับทั้งข้อความ รูปภาพ และเสียง แต่ต้องระบุค่านั้นซ้ำอย่างชัดเจนในตัวแปรทั้งสามของ A เพราะ Servio ไม่ยืมคีย์ข้ามบริการ

สร้างคีย์ลงไฟล์ที่ root อ่านได้ โดยไม่ใส่คีย์ลงใน arguments ของ process:

```sh
sudo install -d -m 0700 /etc/servio-embedding
sudo sh -c 'umask 077; openssl rand -hex 32 > /etc/servio-embedding/api-key'
```

อย่ารันคำสั่งสร้างคีย์ซ้ำบนระบบที่ใช้งานอยู่ เว้นแต่กำลังหมุนเวียนคีย์ ส่งคีย์จากไฟล์นี้ไปผู้ดูแล A ผ่านช่องทางจัดการ secrets ที่ได้รับอนุญาต ไม่ใส่ใน Git, ticket หรือ log

สร้างไฟล์ map ที่ Nginx อ่าน โดยไม่พิมพ์คีย์ออกหน้าจอ:

```sh
sudo python3 - <<'PY'
from pathlib import Path
key = Path('/etc/servio-embedding/api-key').read_text().strip()
assert len(key) == 64 and all(c in '0123456789abcdef' for c in key)
path = Path('/etc/nginx/servio-embedding-keys.map')
path.write_text('"Bearer ' + key + '" 1;\n')
path.chmod(0o600)
PY
```

คัดลอก [embedding-gateway.nginx.conf](examples/embedding-gateway.nginx.conf) ไปยัง `/etc/nginx/conf.d/servio-embedding.conf` ซึ่งต้องถูก include ภายใน `http` context ของ Nginx ปรับ server name, IP ที่อนุญาต และ path ของ certificate ให้ตรงกับเครื่องจริง ติดตั้ง full certificate chain และ private key ตาม path ในไฟล์ก่อนตรวจ config

```sh
sudo nginx -t
sudo systemctl reload nginx
```

ไฟล์ตัวอย่างตั้ง `map_hash_bucket_size=128` เพื่อรองรับคีย์ยาว 64 ตัวอักษร หาก `http` context มี directive นี้อยู่แล้ว ให้ปรับค่าที่มีอยู่ให้เพียงพอและไม่ประกาศซ้ำ

Gateway นี้รับเฉพาะ `/health`, `/props` และ `/v1/embeddings` ตรวจคีย์ทั้งสามเส้นทาง และไม่ส่งคีย์ต่อไปยัง inference ที่ loopback ไม่มีการเปิดหน้า Web UI หรือ API อื่นของ llama-server ดูพฤติกรรม proxy ใน [เอกสาร Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)

ตัวอย่างอนุญาต body สูงสุด 32 MiB และ upstream timeout 200 วินาที ซึ่งเผื่อข้อมูล base64 ของ client ปัจจุบันแล้ว ไม่ใช่ขนาดไฟล์อัปโหลดของ Servio ทดสอบภาพและเสียงขนาดใช้งานจริงก่อนเพิ่มขีดจำกัด

## 4. ติดตั้ง Servio และกำหนด `.env` บน Host A

```sh
git clone https://github.com/rujirapongsn2/servio.git
cd servio
cp .env.example .env
chmod 600 .env
```

สำหรับระบบเดิม ให้เก็บ `.env` เดิมและเพิ่มเฉพาะค่าที่ต้องเปลี่ยน ห้ามคัดลอกทับ secrets หรือเปลี่ยน JWT secret โดยไม่วางแผน session ที่ใช้งานอยู่

ใช้ [production-servio.env.example](examples/production-servio.env.example) เป็นรายการค่าตัวอย่าง นำไปรวมกับ `.env` แล้วแทนที่ค่าที่ขึ้นต้น `REPLACE_WITH_` ทั้งหมดก่อนเริ่มบริการ ตั้งค่าขั้นต่ำสำหรับ Embedding ดังนี้:

```dotenv
EMBEDDING_BASE_URL=https://embedding.internal.example/v1
EMBEDDING_API_KEY=REPLACE_WITH_EMBEDDING_GATEWAY_KEY
MULTIMODAL_EMBEDDING_BASE_URL=https://embedding.internal.example/v1
MULTIMODAL_EMBEDDING_API_KEY=REPLACE_WITH_EMBEDDING_GATEWAY_KEY
AUDIO_EMBEDDING_BASE_URL=https://embedding.internal.example/v1
AUDIO_EMBEDDING_API_KEY=REPLACE_WITH_EMBEDDING_GATEWAY_KEY
```

ใส่เฉพาะค่าคีย์ ไม่ใส่คำว่า `Bearer` เพราะ client เติมให้เอง คีย์ว่างหมายถึงไม่ส่ง Authorization header หากแยก endpoint หรือ gateway ต่อประเภท สามารถใช้คีย์ต่างกันได้ ไม่มี fallback ไป `OPENAI_API_KEY` หรือ `GROQ_API_KEY`

กำหนด model ID ทั้งสามให้ตรงกับ alias บน B (`ggml-org/embeddinggemma-2-GGUF:BF16` ในตัวอย่างนี้) ตั้ง `MULTIMODAL_EMBEDDING_SPACE` และ `AUDIO_EMBEDDING_REVISION` ให้ระบุชุด weights/projector จริง ก่อนเปิดเสียง ค่าขนาด Vector ต้องเป็น 768 มิติ การเปลี่ยน URL หรือคีย์อย่างเดียวโดยใช้โมเดลเดิมไม่ต้อง Re-index แต่การเปลี่ยน weights, projector, prefix หรือ Vector space ต้อง Re-index ประเภทที่เปลี่ยน

`host.docker.internal` และ `127.0.0.1` ไม่ใช่ IP ของ B ใช้ DNS ของ B ตามตัวอย่างแทน Frontend ไม่ต้องรู้คีย์หรือ URL ของ Embedding และอย่ากำหนด secrets ใน `NEXT_PUBLIC_*`

ถ้าใช้ Internal CA ให้สร้าง `docker-compose.override.yml` บน A:

```yaml
services:
  backend:
    volumes:
      - /etc/servio/certs/internal-ca-bundle.pem:/etc/servio/internal-ca-bundle.pem:ro
```

เพิ่ม `SSL_CERT_FILE=/etc/servio/internal-ca-bundle.pem` ใน `.env` ไฟล์นี้ต้องเป็น CA bundle ที่เชื่อถือทั้ง B และ API อื่นที่ Backend ใช้ หากใช้ certificate ที่ระบบเชื่อถืออยู่แล้ว ไม่ต้องเพิ่ม override นี้ ตรวจ DNS และ `HTTPS_PROXY`/`NO_PROXY` ของ container โดยไม่พิมพ์ secrets จาก environment

ตั้งโดเมน Servio, CORS, API key ของ LLM, JWT secret และรหัสผ่าน PostgreSQL แล้วติดตั้ง:

```sh
./services.sh install
./services.sh status
```

ล็อกอินด้วยบัญชีผู้ดูแลที่ตัวติดตั้งจัดเตรียมและเปลี่ยนรหัสผ่านก่อนเปิดให้ใช้งานจริง

ตรวจตัวเลือกของตัวติดตั้งด้วย `./services.sh help` ตัวติดตั้งเก็บ `.env` เดิมเมื่อเลือกไม่ตั้งใหม่ ค่า `NEXT_PUBLIC_*` ถูกฝังตอน build หากเปลี่ยนภายหลังให้ Rebuild Frontend ส่วนการแก้ Embedding URL หรือคีย์ใช้ `./services.sh restart backend` เพื่อ recreate container พร้อม environment ใหม่

### เพิ่ม Audio Processor เมื่อใช้เสียง

Audio Processor ไม่ใช่ Embedding Service และยังไม่รองรับ Bearer key ของตัวเอง ให้รันบน A หรือเครือข่ายที่เชื่อถือและจำกัดการเข้าถึง ไม่ใส่ URL ของ B หรือ Groq ลง `AUDIO_PROCESSOR_BASE_URL` แทน

ติดตั้ง Python environment, FFmpeg, Whisper และ VAD ตาม [คู่มือ Audio Processor](local-knowledge-audio.md) ตั้ง `KNOWLEDGE_AUDIO_ASR_PROVIDER=local` เป็นค่าเริ่มต้น ระบุ path และ revision จริง แล้วเลือก IP บน host ที่ Backend container เข้าถึงได้:

```sh
export KNOWLEDGE_AUDIO_BIND=10.20.0.10
./scripts/run_audio_processor.sh
```

เพิ่มให้ Backend container รู้จัก host A ใน `docker-compose.override.yml` เดิม โดยรวมเป็น `services.backend` ก้อนเดียว:

```yaml
services:
  backend:
    extra_hosts:
      - "servio-host:10.20.0.10"
```

ตัวอย่างใช้ Private IP ของ host โดยตรง จึงไม่พึ่ง Docker default bridge gateway เปลี่ยน IP ให้ตรงกับ interface ที่ Processor bind และอนุญาตพอร์ต 8094 จาก subnet ของ Backend container เท่านั้น ใน `.env` ใช้ `AUDIO_PROCESSOR_BASE_URL=http://servio-host:8094` สำหรับ native Backend บน A ใช้ loopback และไม่ต้องเพิ่ม `extra_hosts`

เมื่อ `/health` ของ Processor พร้อมและตั้ง Audio Embedding revision ถูกต้องแล้ว ให้เปิด `LOCAL_KNOWLEDGE_AUDIO_ENABLED=true` จากนั้น recreate Backend จัดให้ Processor เริ่มอัตโนมัติด้วยตัวจัดการ service ของ OS ตัวอย่าง Mac LaunchAgent อยู่ในคู่มือเสียง อย่าอาศัย terminal ที่อาจถูกปิด

หากเลือก Groq ให้ตั้ง provider กับคีย์ตามคู่มือเสียงแล้วรีสตาร์ต Processor โดยทราบว่าเสียงจะถูกส่งไป Groq การเปลี่ยนนี้ไม่เปลี่ยน Audio Embedding บน B และไม่เปลี่ยนข้อมูลที่นำเข้าแล้ว

## 5. ทดสอบจากเครือข่ายของ Backend จริง

เริ่มด้วยการตรวจ DNS และ TLS จาก container ไม่ใช้ `curl -k`:

```sh
docker compose exec -T backend /app/.venv/bin/python - <<'PY'
import socket
import httpx
print(socket.gethostbyname('embedding.internal.example'))
response = httpx.get('https://embedding.internal.example/health', timeout=5)
print('TLS/HTTP reachable; anonymous status:', response.status_code)
PY
```

เมื่อเปิด gateway ตามตัวอย่าง คำขอที่ไม่มีคีย์ต้องได้ 401 ถ้าได้ 403 ให้ตรวจ IP allowlist ก่อน ขั้นนี้ยังไม่ได้พิสูจน์ว่าคีย์ถูกต้องหรือสร้าง Vector ได้

ใช้ [เครื่องมือตรวจการเชื่อมต่อ](../scripts/check-embedding-services.py) ซึ่งอ่านคีย์จาก environment ของ Backend และเรียก client เดียวกับระบบจริง ไม่มีการบันทึก Knowledge หรือแก้ฐานข้อมูล:

```sh
docker compose exec -T backend /app/.venv/bin/python - --types text image audio --check-auth < scripts/check-embedding-services.py
```

ผลที่คาดหวังคือ `PASS text`, `PASS image`, `PASS audio` และ exit code 0 เครื่องมือตรวจ:

- `/health` และ `/props` ด้วยคีย์ของแต่ละบริการ รวมถึง capability ภาพและเสียง
- การสร้าง Vector จากข้อความ ภาพสีสังเคราะห์ และ WAV เงียบสังเคราะห์ พร้อมการค้นหาด้วยข้อความ
- คำขอ `/v1/embeddings` ที่ไม่มีคีย์ถูกปฏิเสธด้วย 401 หรือ 403

หากยังไม่ได้เตรียมเสียง ใช้ `--types text image` ก่อน เมื่อ Audio Processor พร้อมเพิ่ม `--processor` เพื่อตรวจ readiness โดยไม่ถอดเสียงจริง

สำหรับ native Backend ให้รันจาก root repository โดยเลือก `.env` ที่ตั้ง URL สำหรับ native:

```sh
server/.venv/bin/python scripts/check-embedding-services.py --env-file .env --types text image audio --check-auth --processor
```

เครื่องมือไม่แสดงคีย์ response body หรือ Vector หากล้มเหลวจะแสดงชื่อประเภทและขั้นตอนที่ไม่ผ่าน Environment ที่ export ไว้มีลำดับความสำคัญสูงกว่า `.env` จึงต้องตรวจตัวจัดการ service ด้วยหากค่าที่แก้ไม่ถูกนำไปใช้

### ตรวจรับผ่านหน้า Servio

1. ตรวจ `https://servio.example.com/api/health` และล็อกอิน Admin
2. เปิด Add Knowledge ตรวจว่าเอกสารพร้อม ภาพพร้อม และเสียงพร้อมเมื่อเปิดฟีเจอร์เสียงแล้ว สถานะเอกสารพร้อมหมายถึงนำเข้าเอกสารได้ ไม่ได้ยืนยันว่า Text Embedding ติดต่อได้
3. นำเข้าเอกสาร ภาพ และเสียงตัวอย่างที่ไม่มีข้อมูลลูกค้า ตรวจว่างานสำเร็จและไม่มี Index warning
4. ผูก Knowledge กับ Agent แล้วถามด้วยข้อความ ตรวจคำตอบ แหล่งอ้างอิง ภาพต้นฉบับ และเสียงอ้างอิงหลังคำตอบ
5. ทดสอบแนบภาพเพื่อค้นหาใน Web Chat บน Desktop และมือถือ ด้วยภาพตัวอย่างที่รู้ผลลัพธ์
6. หากย้ายระบบเดิม ให้ค้นหาข้อมูลเดิมซ้ำก่อนเปิดรับ traffic จริง เก็บค่าต้นทางเดิมไว้สำหรับ rollback

Health และ Vector smoke test ไม่ได้ยืนยันคุณภาพคำตอบหรือประสิทธิภาพเมื่อมีผู้ใช้พร้อมกัน ทดสอบคำถามและโหลดตามการใช้งานจริงก่อนรับรองระบบ

## 6. แก้ปัญหาและดูแลระบบ

| อาการ | ตรวจสอบ |
| --- | --- |
| Resolve DNS ไม่ได้ | DNS ใน container, routing และ Private DNS zone |
| TLS verification failed | Hostname, full chain, เวลาเครื่อง และ CA bundle ภายใน container |
| 401 | คีย์ทั้งสามตรงกับ map, ไม่ใส่ Bearer ซ้ำ, ไม่มีช่องว่างภายในคีย์ และ Backend ถูก recreate แล้ว |
| 403 | IP allowlist/NAT, Firewall และ HTTP method ที่ gateway อนุญาต |
| 404 หรือ redirect | ใช้ base `/v1` และเปิด `/health`, `/props` ที่ root ของ hostname โดยไม่ redirect |
| ภาพ/เสียง Unavailable | Flag, revision ของเสียง, key ของ probe, modalities ใน `/props` และ Processor readiness |
| Health ผ่าน แต่สร้าง Vector ไม่ได้ | Model ID, weights/projector, multimodal request format, body limit, GPU memory และ log ฝั่ง B |
| 413 | Body limit ของ gateway ต้องเผื่อ base64 ไม่ใช่เฉพาะไฟล์ต้นฉบับ |
| Timeout หรือ 5xx | Queue, GPU contention, latency และ proxy timeout; อย่าเพิ่ม timeout โดยไม่ตรวจ bottleneck |
| เปลี่ยน `.env` แล้วเหมือนเดิม | Recreate Backend, process environment ที่ override ค่า และรีสตาร์ต Processor แยกเมื่อเปลี่ยนค่าของมัน |

Health probes ภาพและเสียงมีเวลารวมประมาณ 1.8 วินาที ส่วน Embedding request ค่าเริ่มต้นคือข้อความ 60 วินาที ภาพและเสียง 180 วินาที จัดให้เส้นทาง readiness ตอบได้แม้ inference มีโหลด ไม่แสดงพร้อมเมื่อโมเดลยังโหลดไม่เสร็จ

สำรอง `postgres_data`, ไฟล์ `server/data`, `.env` ในที่จัดเก็บ secrets และข้อมูล revision ของโมเดล อย่าใส่คีย์จริงใน repository ไม่เปิด request-body/header logging บน gateway

การหมุนเวียนคีย์ให้เพิ่มคีย์ใหม่ใน map โดยเก็บคีย์เดิมชั่วคราว ตรวจ `nginx -t` แล้ว reload เปลี่ยนคีย์บน A, recreate Backend และรันเครื่องมือตรวจซ้ำ เมื่อทุก instance ใช้คีย์ใหม่จึงลบคีย์เดิมและ reload การหมุนคีย์ไม่ต้อง Re-index

หากต้อง rollback URL ให้คืนค่า endpoint และคีย์เดิมแล้ว recreate Backend หากมีการเปลี่ยนชุดโมเดลด้วย ต้องคืน Vector space/revision และ index ที่เข้าคู่กัน ไม่เปรียบเทียบ Vector ข้ามโมเดลเพียงเพราะมี 768 มิติเท่ากัน
