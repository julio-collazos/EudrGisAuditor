import os
from app.main import app

HOST = '0.0.0.0'
PORT = 5000

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
