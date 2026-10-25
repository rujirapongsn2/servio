# กู้คืน Knowledge ที่ขาดไฟล์ต้นฉบับ

คู่มือนี้ใช้กับ Production ที่ `https://servio.softnix.ai` ซึ่ง audit วันที่ 25 ตุลาคม 2026 รายงานว่า 44 จาก 103 bundles ขาดโฟลเดอร์ต้นฉบับ รวมถึง bundle 71 และ 88 ของทีม ART_2 (282) ตัวเลขเหล่านี้เป็นผลจาก audit ครั้งนั้น ต้องตรวจสถานะปัจจุบันอีกครั้งก่อนกู้คืน

## พฤติกรรมหลังอัปเดตโค้ด

API รายการและรายละเอียด bundle คืน `source_availability` แยกจาก `status` ที่บันทึกตอนนำเข้า โดยตรวจโฟลเดอร์และไฟล์ Markdown ที่ดัชนีอ้างอิง

| `source_availability.status` | ความหมาย |
| --- | --- |
| `available` | พบไฟล์ต้นฉบับที่อ้างอิงและตรวจสิทธิ์อ่านผ่าน |
| `missing` | ไม่พบโฟลเดอร์ต้นฉบับ |
| `partial` | โฟลเดอร์ยังอยู่ แต่ขาดไฟล์ต้นฉบับบางรายการ |
| `unreadable` | ตรวจพาธหรือสิทธิ์อ่านไม่ผ่าน |

`missing_file_count` คือจำนวน Markdown ที่ตรวจพบว่าหาย ไม่ใช่การตรวจ checksum หรือยืนยันว่าไฟล์ภาพ/เสียงประกอบครบทั้งหมด

เมื่อไฟล์ขาด หน้า Knowledge แสดงคำแนะนำการกู้คืนและปิดการแก้ไข/reindex แต่ยังเปิดรายการเอกสารและค้นจากข้อมูล cache ได้ตามข้อมูลที่ยังเหลือ การเปิดเอกสารที่ต้นฉบับหายคืน HTTP 409 พร้อมข้อความที่ไม่เปิดเผยพาธบนเซิร์ฟเวอร์ การ reindex ทั้งชุดและ vector reindex จะหยุดก่อนเขียนทับดัชนี

โค้ดไม่เปลี่ยน persisted import status, ลบ cache หรือสร้างไฟล์ต้นฉบับทดแทนให้เอง เมื่อกู้ไฟล์กลับถูกตำแหน่ง สถานะจะปรับตามการตรวจครั้งถัดไป

## ขั้นตอนสำหรับ agent บน Production

1. บันทึก commit ปัจจุบันและตรวจ `git status --short` ก่อนอัปเดต รักษาการปรับ Docker/Audio ของ Production ที่มีอยู่ ห้ามใช้ `git reset --hard`, `git clean` หรือเขียนทับ `.env` เพื่อแก้ conflict
2. นำชุดแก้ไขเข้า checkout โดยตรวจ diff ก่อน build หากพบ conflict กับการปรับ deployment เดิม ให้แก้เฉพาะส่วนที่เกี่ยวข้องและบันทึกสิ่งที่รักษาไว้
3. ตรวจว่าไม่มี import job ที่กำลังทำงาน แล้ว build/restart ทั้ง backend และ frontend ตามวิธี deploy ของ Production ตัวอย่างสำหรับ Compose คือ `./services.sh rebuild backend` แล้ว `./services.sh rebuild frontend` ตรวจ `./services.sh status` และ health ของ URL จริงหลังเริ่มบริการ
4. ตรวจรายการไฟล์ที่หายแบบอ่านอย่างเดียวด้วยคำสั่งด้านล่าง อย่าใช้การ reindex เป็นวิธีตรวจต้นฉบับก่อนอัปเดตโค้ด
5. สำรอง PostgreSQL และโฟลเดอร์ Knowledge ปัจจุบันก่อนกู้ข้อมูลจริง ตรวจว่า backup ที่จะนำมาคืนเป็นชุดเดียวกับ metadata และดัชนีในฐานข้อมูล
6. คืน source ที่ตรงกันจากเครื่องเดิม/backup หรือให้เจ้าของข้อมูลนำเข้า originals ใหม่ หากยังหา originals ไม่ได้ ให้คง cache เดิมไว้และรายงานรายการที่ขาด ห้ามลบ bundle หรือ reindex จาก source ที่เหลือไม่ครบ
7. หลังคืน source แล้ว ตรวจสถานะใหม่ก่อน reindex สำหรับไฟล์ภาพและเสียง ให้ตรวจไฟล์ประกอบใน `assets/` ด้วย หากเนื้อหาถูกเปลี่ยน ให้ใช้ source reindex เพื่อสร้างดัชนีเนื้อหาใหม่ก่อนสร้าง vectors

Production audit ระบุ mount `./server/data:/app/data` และพาธในคอนเทนเนอร์ `/app/data/okf_bundles/{id}/source` ดังนั้นพาธ host ที่คาดหมายคือ `server/data/okf_bundles/{id}/source` ต้องยืนยัน mount และ `storage_path` จริงก่อนคัดลอกไฟล์

```sh
docker compose exec -T backend /app/.venv/bin/python - <<'PY'
import json
from app.okf_service import OKFService

for bundle in OKFService().list_bundles(None):
    availability = bundle["source_availability"]
    if availability["status"] != "available":
        print(json.dumps({
            "id": bundle["id"],
            "team": bundle["owner_team_agent_id"],
            "import_status": bundle["status"],
            "source": availability,
        }, ensure_ascii=False))
PY
```

คำสั่งนี้ใช้สิทธิ์ฐานข้อมูลของ backend เพื่ออ่านรายการทุกทีม ไม่อ่านเนื้อหาเอกสารและไม่แก้ข้อมูล หากใช้ชื่อ Compose service หรือพาธ Python ต่างจากตัวอย่าง ให้ปรับตาม deployment จริง

## ทดสอบหลัง deploy

ใช้ฐานข้อมูลชื่อ `servio_knowledge_checks_*` และโฟลเดอร์ source ชั่วคราวสำหรับการสร้าง/ลบ fixtures ไม่สร้างการทดสอบที่ทำให้ source ของลูกค้าหาย

- นำเข้าเอกสารอย่างน้อยสองไฟล์ แล้วตรวจ preview, import job, assignment, retrieval และ vector indexing
- ในฐานทดสอบ เปลี่ยนชื่อ source directory แล้วตรวจ bundle API แสดง `missing` โดย import status เดิมยังอยู่ ตรวจ concept detail และ reindex ทั้งสองแบบคืน 409 และ cache/vector rows ไม่เปลี่ยน
- ทดสอบลบ Markdown เพียงหนึ่งไฟล์ ตรวจสถานะ `partial` เอกสารที่ยังอยู่เปิดได้ และการแก้ไข/reindex ไม่ลบดัชนีของไฟล์ที่ขาด
- คืนไฟล์ แล้วตรวจสถานะ `available` และ reindex สำเร็จ
- ตั้ง environment เฉพาะ backend ทดสอบเป็น `LOCAL_KNOWLEDGE_AUDIO_ENABLED=true`, text hybrid และ images เป็น false นำเข้าเสียงตัวอย่าง แล้วเรียก `POST /api/admin/okf-bundles/{id}/reindex-vectors` ต้องได้ HTTP 200, aggregate `status=ready` และ `audio_index.status=ready` ตรวจ retrieval และ signed HTTP Range playback
- ตรวจรูปภาพ, ข้อความ/เสียงอ้างอิง และสิทธิ์ข้ามทีม ด้วย fixtures ที่ไม่มีข้อมูลลูกค้า
- ตรวจผ่านเบราว์เซอร์ Desktop และมือถือว่า warning อ่านได้ ปุ่ม reindex ถูกปิดพร้อมเหตุผล และสลับไปเปิดเอกสารที่ยังอยู่ได้

API และ component regressions ที่เกี่ยวข้องรันได้ดังนี้ ชุดทดสอบที่ต้องเปิดพอร์ต localhost ต้องรันใน environment ที่อนุญาต

```sh
cd server
.venv/bin/python -m pytest tests/test_okf_source_integrity.py tests/test_okf_api_scope.py tests/test_knowledge_audio.py tests/test_knowledge_images.py tests/test_knowledge_urls.py -q
```

```sh
cd frontend
node --test tests/knowledge-document-drawer.test.mjs tests/knowledge-audio.test.mjs tests/knowledge-document-image.test.mjs
```

การ์ด Ready ใน Add Knowledge บอกความพร้อมรับไฟล์ใหม่ ไม่ใช่ผลตรวจต้นฉบับของ bundles เดิม ส่วน JPG/PNG OCR, Image Q&A และ product category rerank ต้องตั้ง Vision model และเปิด flags ที่เกี่ยวข้องแยกต่างหาก ห้ามเปิด flags หรือส่งข้อมูลลูกค้าไปยัง provider เพิ่มโดยอัตโนมัติระหว่าง deploy ชุดแก้ไขนี้

## ผลตรวจจากเครื่องพัฒนา

ชุดแก้ไขนี้มี regression สำหรับต้นฉบับหายทั้งโฟลเดอร์/บางไฟล์, สิทธิ์อ่าน, cache/link preservation, การคืน source และ audio-only API reindex พร้อมทดสอบผ่าน handlers จริงกับ PostgreSQL/pgvector และ Embedding Service ผลตรวจบนเครื่องพัฒนาไม่ใช่การยืนยันว่า Production กู้ source ครบหรือทดสอบเบราว์เซอร์ผ่านแล้ว

พบสอง tests เดิมของ `tests/test_team_agents.py` ที่ไม่ผ่านบนฐานทดสอบแยก ได้แก่ `TestRuntimeAgentResolution::test_resolve_without_team` และ `TestChannelConfigs::test_team_channel_isolation` ทดสอบซ้ำบนโค้ดก่อนแก้ commit `93303cd` แล้วได้ผลเดียวกัน ต้องรายงานแยกจากการตรวจ Knowledge ไม่แก้ assertions เพื่อให้ผลผ่าน
