# Prompt ติดตั้ง Intent Decision Maker บน MacBook Air M4

คัดลอกข้อความตั้งแต่หัวข้อ “คำสั่งสำหรับ Agent” ให้ AI Agent บน MacBook Air M4 ใช้ตัวติดตั้งจาก [คู่มือ Decision Maker](../intent-decision-maker.md) โดยไม่ติดตั้งระบบ Servio ส่วนอื่น

## คำสั่งสำหรับ Agent

คุณเป็น AI Agent ที่ทำงานบน MacBook Air M4 ให้ติดตั้งเฉพาะ MediaPipe Decision Maker และ EmbeddingGemma 2 แบบ native macOS โดยใช้ Metal GPU พร้อม API key และเริ่มบริการอัตโนมัติหลังผู้ใช้ login

ให้ลงมือทำและทดสอบจริง ไม่ใช่เพียงเสนอแผน รายงานตามหลักฐานที่ตรวจได้ และแยกสิ่งที่ผ่านแล้วออกจากสิ่งที่ยังรอสิทธิ์เข้าถึง

### 1. ขอบเขตงานและการเชื่อมต่อ

เส้นทางที่ต้องใช้งาน:

```text
Servio Backend บน Production
→ https://intent01.softnix.ai
→ Cloudflare Tunnel ที่ตั้งค่าไว้แล้ว
→ http://127.0.0.1:8095
→ MediaPipe Decision Maker + EmbeddingGemma 2 บน Metal GPU
```

งานของคุณมีเฉพาะติดตั้งบริการ Decision Maker บน MacBook Air M4 และตรวจว่าเรียกผ่าน local endpoint กับ public endpoint ได้

ข้อกำหนด:

- ไม่ติดตั้ง Servio Backend, Frontend, PostgreSQL หรือ Docker
- ไม่ติดตั้ง Embedding API server เพิ่ม
- ไม่แก้ไข Production Server หรือ `.env` ของ Production
- ไม่แก้ไข Cloudflare Tunnel, DNS, routing หรือ credentials เพราะตั้งค่า `intent01.softnix.ai → http://127.0.0.1:8095` ไว้แล้ว
- ไม่ติดตั้ง Nginx, Caddy, reverse proxy หรือ SSL certificate บน Mac เพิ่ม
- ไม่แก้ไข หยุด หรือ restart บริการอื่น รวมถึงพอร์ต 8090 หากมีอยู่
- ไม่เปิด handoff อัตโนมัติ และไม่เพิ่มตรรกะเลือกหรือส่งต่อ Agent
- ต้องใช้ Metal GPU หากใช้ไม่ได้ ให้รายงานปัญหา ห้าม fallback ไป CPU โดยไม่แจ้ง
- ห้ามแสดง API key หรือ credentials ในแชต command line, shell history, logs หรือ Git

### 2. ตรวจเครื่องและเตรียม source

ตรวจว่า macOS และ Python ทำงานแบบ Apple Silicon arm64 native ไม่ผ่าน Rosetta

ตรวจ Git, uv, พื้นที่ดิสก์ หน่วยความจำ และ process ที่ใช้พอร์ต 8095 หากพอร์ตถูกใช้โดยบริการอื่น ให้รายงาน conflict โดยไม่หยุด process นั้น

ใช้โค้ดที่ผ่านการทดสอบจาก:

https://github.com/rujirapongsn2/servio.git

Commit ที่มี implementation:

```text
50ec356600da13bc14fa367725ab35b87d24e0fb
```

ใช้ commit นี้ หรือ revision ใหม่กว่าที่ตรวจแล้วว่า API contract, model checksum และ decision profile ยังตรงกับ Servio Production

สามารถ checkout source ในโฟลเดอร์แยก เช่น `~/Developer/servio-intent-deploy` เพื่อใช้ตัวติดตั้ง แต่ห้ามติดตั้งหรือเปิดบริการอื่นของ Servio

ห้าม clone ทับโครงการเดิม ห้าม reset หรือทิ้งไฟล์ที่ยังไม่ได้ commit ใช้ GitHub authentication ที่มีอยู่ หากเข้า repository ไม่ได้ ให้รายงานสิทธิ์ที่ขาดโดยไม่ขอ token ผ่านแชต

อ่านเฉพาะส่วนที่เกี่ยวข้อง:

- `docs/intent-decision-maker.md`
- `scripts/install_intent_decision_macos.py`
- `scripts/run_intent_decision.sh`
- `server/decision_service/`
- `server/app/intent_contract.py`

ใช้ dependencies ที่ pin ไว้ใน `server/decision_service/requirements.txt` และแยก Python environment จากโปรแกรมอื่น

### 3. เตรียมโมเดลและ API key

โมเดล:

```text
embeddinggemma-2-text-270m.litertlm
```

ดาวน์โหลดจาก:

https://huggingface.co/litert-community/embeddinggemma-2-text-270m-litert-lm/resolve/main/embeddinggemma-2-text-270m.litertlm

ตำแหน่งเริ่มต้นใน source checkout:

```text
server/decision_service/models/embeddinggemma-2-text-270m.litertlm
```

SHA256 ที่ต้องตรง:

```text
2d079ee2f6f066b1f368e8d7c819f55214eaef1d0513b312321901f30ab286fb
```

ดาวน์โหลดลงไฟล์ชั่วคราว ตรวจ checksum แล้วจึงย้ายเข้าตำแหน่งจริง ถ้ามีไฟล์ที่ถูกต้องอยู่แล้วให้ใช้ของเดิม ห้ามใช้ไฟล์ GGUF แทน และห้ามข้าม checksum validation

สร้าง API key เฉพาะบริการด้วยค่าการสุ่มอย่างน้อย 32 bytes เช่น `secrets.token_hex(32)` หากมี key ของบริการนี้ใช้งานอยู่แล้วให้รักษาค่าเดิม

บันทึก `.env` ใน source checkout ด้วยสิทธิ์ 600 โดยไม่แสดง key:

```dotenv
INTENT_DECISION_API_KEY=<dedicated-random-key>
INTENT_DECISION_BIND=127.0.0.1
INTENT_DECISION_PORT=8095
INTENT_DECISION_MODEL_PATH=
```

`MODEL_PATH` ว่างหมายถึงใช้ตำแหน่งโมเดลเริ่มต้นข้างต้น

อย่าใส่ key ใน URL หรือ LaunchAgent plist และอย่านำ key ของ Embedding, LLM หรือ Cloudflare มาใช้ซ้ำ

ไม่ต้องตั้ง `INTENT_DECISION_ENABLED` บน Mac เพราะเครื่องนี้รันเฉพาะบริการ Decision Maker ไม่มี Servio Backend

### 4. ติดตั้ง native service และเริ่มอัตโนมัติ

ใช้ตัวติดตั้งที่มีอยู่จาก root ของ source checkout:

```sh
uv run --python 3.11 --with python-dotenv==1.0.1 scripts/install_intent_decision_macos.py
```

ตัวติดตั้งต้องสร้าง runtime แยกใต้:

```text
~/Library/Application Support/Servio/IntentDecision
```

และ LaunchAgent:

```text
~/Library/LaunchAgents/ai.softnix.servio.intent-decision.plist
```

ตรวจว่า:

- ใช้ Python environment แยกสำหรับ native service
- runtime มีเฉพาะไฟล์ที่ Decision Maker ต้องใช้
- `.env` ของ runtime มีสิทธิ์ 600
- ไม่มี key ใน plist
- `deployment.json` ระบุ release และ source hashes ถูกต้อง
- process ฟังเฉพาะ `127.0.0.1:8095`
- มีเพียงหนึ่ง process ของบริการนี้
- การอัปเดตเตรียม release ใหม่ก่อนหยุดบริการเดิม และมี rollback หากเริ่มไม่สำเร็จ

LaunchAgent เริ่มหลังผู้ใช้ login หาก reboot เครื่อง ต้องมี user session ก่อนบริการจึงเริ่มได้ อย่าเปิด automatic macOS login เปลี่ยน FileVault หรืออ้างว่าบริการเริ่มก่อน login

ทดสอบ restart เฉพาะ LaunchAgent ของ Decision Maker และตรวจว่า readiness กลับมาได้ ไม่ต้อง reboot เครื่องจริงในงานนี้

### 5. ตรวจ Metal GPU และ Local API

อ่าน log จาก release ที่ `deployment.json` ระบุ เช่น:

```text
server/decision_service/.cache/service.stderr.log
```

ต้องมีหลักฐาน Metal initialization เช่น:

- `Created a Metal device`
- `Metal Residency Set successfully initialized`
- `Initializing Metal-based API`

จากนั้นต้องทดสอบ inference จริงสำเร็จด้วย ค่า `delegate_requested=GPU` เพียงอย่างเดียวยังไม่ถือว่ายืนยัน GPU แล้ว

บริการต้องมี endpoints:

```text
GET  http://127.0.0.1:8095/health
POST http://127.0.0.1:8095/v1/intent
```

ทั้งสอง endpoint ต้องตรวจ:

```text
Authorization: Bearer <INTENT_DECISION_API_KEY>
```

อ่าน key จากไฟล์ภายในโปรแกรมทดสอบ ห้ามใส่ key จริงลง command line หรือพิมพ์ request headers ที่มี key

ทดสอบ:

- ไม่มี key ได้ HTTP 401
- key ผิดได้ HTTP 401
- key ถูกต้องเรียก health ได้ HTTP 200 และ `ready=true`
- `model_sha256` และ `profile` ตรงกับ contract ใน source
- inference สำเร็จและคืนผลตาม API contract

ตัวอย่าง request:

```json
{
  "schema_version": 1,
  "context": "user: ไม่ต้องการคืนเงินครับ ปัญหาหายแล้ว ขอบคุณครับ"
}
```

ผล inference ต้องมี `schema_version`, `profile`, `selected_key`, `confidence` และ `probabilities`

ตรวจว่าคะแนนเป็นค่าตัวเลขที่ถูกต้อง กลุ่มตรงกับ contract และ probabilities รวมประมาณ 1 ใช้ข้อความสังเคราะห์เท่านั้น ไม่ส่งข้อมูลลูกค้าจริง ไม่เปลี่ยนคำถาม โมเดล หรือเกณฑ์เพื่อทำให้ผลทดสอบผ่าน

### 6. ตรวจผ่าน Cloudflare Tunnel ที่มีอยู่

Routing ถูกตั้งไว้แล้ว:

```text
https://intent01.softnix.ai → http://127.0.0.1:8095
```

ห้ามแก้หรือ restart Cloudflare Tunnel ในงานนี้

เมื่อ local API ผ่าน ให้ทดสอบ:

```text
GET  https://intent01.softnix.ai/health
POST https://intent01.softnix.ai/v1/intent
```

ตรวจว่า:

- HTTPS ใช้งานได้โดยไม่ปิด certificate verification
- ไม่มี key หรือ key ผิดถูกปฏิเสธ
- key ถูกต้องได้ HTTP 200
- ได้ JSON จากบริการจริง ไม่มี HTML login page, redirect หรือ challenge ขวาง API
- Authorization header ส่งถึง origin
- health profile ตรงกับ local endpoint
- inference ผ่าน public endpoint สำเร็จ

หาก local API ผ่านแต่ public endpoint ไม่ผ่าน ให้แยกสาเหตุเป็น DNS, Tunnel, routing หรือ Access policy จากหลักฐานที่ตรวจได้ แล้วรายงานให้ผู้ดูแลแก้ ห้ามเปลี่ยน Cloudflare configuration เอง

ถ้าพบว่าต้องใช้ Cloudflare Access service-token headers เพิ่ม ให้รายงาน เพราะ Servio client ปัจจุบันส่ง Bearer key เท่านั้น อย่าปิด security policy เพื่อให้ทดสอบผ่าน

ทดสอบข้อความไทยสั้นหลายกรณีแบบเรียงทีละคำขอ และบันทึกเวลาตอบจริง รวมทั้ง timeout หรือ HTTP errors อย่าอ้าง latency ของ Production จากผลที่วัดบน Mac เพียงเครื่องเดียว

### 7. ส่งมอบข้อมูลให้ Agent ฝั่ง Production

ไม่ต้องเชื่อมต่อหรือแก้ไข Production Server ให้เตรียมค่าต่อไปนี้สำหรับผู้ดูแลหรือ Agent ฝั่ง Production:

```dotenv
INTENT_DECISION_ENABLED=true
INTENT_DECISION_BASE_URL=https://intent01.softnix.ai
INTENT_DECISION_API_KEY=<same-dedicated-key-as-Mac-M4>
INTENT_DECISION_TIMEOUT_SECONDS=1.5
INTENT_DECISION_MIN_CONFIDENCE=0.75
INTENT_DECISION_MIN_PROBABILITY=0.85
INTENT_DECISION_MIN_MARGIN=0.30
```

`BASE_URL` ต้องไม่มี `/v1` หรือ `/v1/intent` ต่อท้าย เพราะ Servio client เติม `/v1/intent` เอง

ค่าเหล่านี้เป็นคำแนะนำสำหรับ Backend ฝั่ง Production ไม่ใช่ค่าที่ต้องเปิดใช้บน Mac เครื่องนี้

ห้ามแสดง key จริงในรายงาน แจ้งเฉพาะตำแหน่งไฟล์สิทธิ์ 600 ที่ผู้ดูแลสามารถนำ key ไปส่งผ่านช่องทางลับได้

ระบุว่าฝั่ง Production ยังต้อง:

- มีโค้ด Intent Decision integration ที่เข้ากันได้
- ตั้ง key ให้ตรงกับบริการบน Mac
- โหลด environment ใหม่ตามวิธี deploy ของระบบ
- ทดสอบจาก Backend runtime หรือ container จริง
- รักษา Keywords เป็นด่านแรกและ LLM เป็น fallback
- ไม่เปิด handoff อัตโนมัติ
- ไม่เปลี่ยนค่า Embedding Service เดิม

ห้ามรายงานว่า Production เชื่อมต่อสำเร็จ เพราะงานนี้ไม่ได้เข้าไปทดสอบจาก Production

### 8. รายงานผลสุดท้าย

รายงานโดยไม่เปิดเผย secrets:

1. Source revision, Python และ MediaPipe versions
2. ชื่อโมเดลและ SHA256
3. หลักฐาน Metal initialization และ inference จริง
4. ตำแหน่ง runtime, release, LaunchAgent และ logs
5. PID และ listener `127.0.0.1:8095`
6. ผล local API และ public API แยกกัน รวมกรณี key ผิด
7. ผล restart และการกลับมา ready
8. ขั้นตอน restart, update และ rollback เฉพาะ Decision Maker
9. ตำแหน่งไฟล์ API key สำหรับผู้ดูแล โดยไม่แสดงค่า
10. สิ่งที่ยังรอดำเนินการฝั่ง Production

ยืนยันว่าไม่ได้ติดตั้งบริการอื่นของ Servio ไม่แก้ Cloudflare Tunnel ไม่เปลี่ยนบริการอื่น และไม่เปิด handoff อัตโนมัติ หากบางขั้นตอนไม่ผ่าน ให้ระบุสาเหตุและหลักฐาน อย่ารายงานว่าสำเร็จครบทั้งหมด
