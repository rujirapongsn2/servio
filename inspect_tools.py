import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), "server"))

from app.database import get_all_tools

def inspect():
    tools = get_all_tools()
    found = False
    for tool in tools:
        if tool['name'] == 'furniture_catalog':
            found = True
            print(f"Tool found: {tool['name']}")
            print(f"Type: {tool['type']}")
            try:
                config = json.loads(tool['config'])
                print(f"Config: {json.dumps(config, indent=2, ensure_ascii=False)}")
            except:
                print(f"Config (raw): {tool['config']}")
            break
    
    if not found:
        print("Tool 'furniture_catalog' not found in database.")

if __name__ == "__main__":
    inspect()
