import sys
import os

# Add server directory to path so we can import app modules
sys.path.append(os.path.join(os.getcwd(), "server"))

from app.softnix_api import query_softnix_genai

def test():
    print("Testing Softnix API with Thai query...")
    try:
        # Use the query from the user's screenshot
        res = query_softnix_genai("แนะนำโต๊ะทานข้าว ราคาประหยัด มีสินค้าพร้อมส่ง")
        print("Success!")
        print(str(res)[:100] + "...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
