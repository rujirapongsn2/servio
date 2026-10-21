"""Synthetic product API for trying Web Chat cards without a real catalog."""
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.product_presentations import ProductCarousel

app = FastAPI(title="Servio example product catalog")

PRODUCTS=[
 {'id':'DEMO-SPARK-01','title':'หัวเทียน OEM รุ่น A','part_number':'DEMO-9807-A','brand':'DEMO HONDA','price_text':'ราคาทดสอบ 250 บาท','description':'ข้อมูลสินค้าทดสอบสำหรับตรวจ Carousel เท่านั้น หัวเทียน OEM รุ่น A รหัส DEMO-SPARK-01 เกลียวทดสอบ 14 มม. ไม่ใช่คำแนะนำการเลือกอะไหล่จริง','image_url':'https://placehold.co/640x480/png?text=SPARK+01'},
 {'id':'DEMO-SPARK-02','title':'หัวเทียน Iridium รุ่น B','part_number':'DEMO-9807-B','brand':'DEMO NGK','price_text':'ราคาทดสอบ 450 บาท','description':'ข้อมูลสินค้าทดสอบ รุ่น B รหัส DEMO-SPARK-02 วัสดุทดสอบ Iridium พร้อมข้อมูลรายละเอียดจาก API','image_url':'https://placehold.co/640x480/png?text=IRIDIUM+02'},
 {'id':'DEMO-SPARK-03','title':'หัวเทียน Platinum รุ่น C','part_number':'DEMO-9807-C','brand':'DEMO DENSO','description':'ข้อมูลสินค้าทดสอบ รุ่น C ไม่มีราคาจากแหล่งข้อมูล ต้องไม่แสดงราคาที่สร้างขึ้นเอง','image_url':'https://placehold.co/640x480/png?text=PLATINUM+03'},
 {'id':'DEMO-SPARK-04','title':'หัวเทียน Long Life รุ่น D','part_number':'DEMO-9807-D','brand':'DEMO BOSCH','description':'ข้อมูลสินค้าทดสอบรุ่น D สำหรับตรวจการเลื่อน Carousel และภาพที่โหลดไม่สำเร็จ','image_url':'https://example.com/nonexistent-product-image.png'},
 {'id':'DEMO-SPARK-05','title':'หัวเทียนสำหรับตรวจข้อความชื่อสินค้าที่ยาวบนจอขนาดเล็ก รุ่น E','part_number':'DEMO-9807-E','brand':'DEMO OEM','description':'รายละเอียดสินค้าทดสอบรุ่น E '+('ข้อความยาวสำหรับทดสอบการเลื่อนอ่านรายละเอียด ' * 20),'image_url':'https://placehold.co/640x480/png?text=LONG+LIFE+05'}]

class CatalogQuery(BaseModel):
    query: str = Field(default="", max_length=2000)


def search_catalog(query: str) -> ProductCarousel:
    matches = [product for product in PRODUCTS if product["id"].lower() in query.lower()]
    return ProductCarousel.model_validate({
        "type": "product_carousel",
        "version": 1,
        "summary": f"พบสินค้าตัวอย่าง {len(matches or PRODUCTS)} รายการสำหรับทดสอบ Web Chat",
        "products": matches or PRODUCTS,
    })


@app.get("/products", response_model=ProductCarousel, response_model_exclude_none=True)
def get_products(query: str = ""):
    return search_catalog(query)


@app.post("/products", response_model=ProductCarousel, response_model_exclude_none=True)
def post_products(request: CatalogQuery):
    return search_catalog(request.query)
