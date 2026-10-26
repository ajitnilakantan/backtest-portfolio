from waitress import serve

from testfolio_dash.application import get_server
from testfolio_dash.config import CONFIG

server = get_server()

if __name__ == "__main__":
    serve(server, host=CONFIG.host, port=CONFIG.port)
