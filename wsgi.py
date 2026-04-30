# # wsgi.py
# from app import app

# if __name__ == "__main__":
#     app.run()


# wsgi.py
from app import app
from a2wsgi import WSGIMiddleware

asgi_app = WSGIMiddleware(app)