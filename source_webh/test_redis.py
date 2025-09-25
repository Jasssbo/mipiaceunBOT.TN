# Quick test script per verificare connessione Redis
import os
import redis
from dotenv import load_dotenv

load_dotenv('bot_infos_webh.env')

def test_redis_connection():
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        print(f"Connessione a Redis...")
        #print(f"Connessione a Redis: {redis_url[:50]}...")
        
        # Test connessione con timeout
        r = redis.from_url(redis_url, decode_responses=True, socket_timeout=10, socket_connect_timeout=10)
        result = r.ping()
        print(f"✅ Redis connection OK! Ping result: {result}")
        
        # Test scrittura/lettura
        r.set("test_key", "test_value", ex=60)
        value = r.get("test_key")
        print(f"✅ Test write/read: {value}")
        
        # Cleanup
        r.delete("test_key")
        print("✅ Test cleanup OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Redis error: {e}")
        return False

if __name__ == "__main__":
    test_redis_connection()