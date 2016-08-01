import signal
from os import path, environ
from concurrent.futures import ThreadPoolExecutor

from time import time, sleep

from tornado import web, gen
from tornado.options import options
from tornado.httpserver import HTTPServer
from tornado.httpclient import HTTPClient
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.iostream import StreamClosedError
from tornado.escape import json_decode, json_encode

class Feeder(object):
    """
    Feeder runs on its own thread
    """
    def __init__(self):
        self.last_data = 'The time is not set'
        self.running = False

    def stop(self):
        self.running = False
        print('Feeder is stopping...')

    def run(self, executor):
        print('Feeder is running...')
        self.running = True

        API_URL = 'http://api.openweathermap.org/data/2.5/weather?q=Singapore&appid=20badc5bc59ff9605424440b0d71b7f3'

        def internal_run():
            """
            Possibly peeking at Facebook feed
            """
            http_client = HTTPClient()
            print('[Feeder.run:internal_run] Running...')
            while self.running:
                print('[Feeder.run:internal_run] Fetch weather data...')
                response = http_client.fetch(API_URL)

                try:
                    data = json_decode(response.body)
                    print('[Feeder.run:internal_run] Found {} weather items'.format(len(data['weather'])))
                    self.last_data = json_encode(dict(weather=data['weather'][0],
                                                      main=data['main'],
                                                      wind=data['wind']))
                except Exception as e:
                    pass
                sleep(10)

        executor.submit(internal_run)

    def subscribe(self, channel):
        pass

    def unsubscribe(self, subscription_id):
        pass

    @gen.coroutine
    def take(self):
        """
        Pull model
        """
        return self.last_data


class LiveFeedApp(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.executor = ThreadPoolExecutor(4)
        self.feeder = Feeder()

    def listen(self, port):
        super().listen(port)
        self.feeder.run(self.executor)

    def stop(self):
        self.feeder.stop()
        self.executor.shutdown(wait=False)


class EventSource(web.RequestHandler):
    def __init__(self, app, request):
        super().__init__(app, request)

        self.set_header('content-type', 'text/event-stream')
        self.set_header('cache-control', 'no-cache')

        self.last_data = None

    @gen.coroutine
    def publish(self, data):
        """Pushes data to a listener."""
        try:
            self.write('data: {}\n\n'.format(data))
            yield self.flush()
        except StreamClosedError:
            pass

    @gen.coroutine
    def get(self):
        # self.application.feeder.subscribe('jobposts')

        while True:
            data = yield self.application.feeder.take()
            if self.last_data == data:
                yield gen.sleep(1)
            else:
                yield self.publish(data)
                self.last_data = data


if __name__ == '__main__':
    base_dir = path.join(path.dirname(__file__), '..')
    static_dir = path.join(base_dir, 'static')

    port = environ.get('PORT', '8888')
    env = environ.get('ENV', 'DEV')
    app = LiveFeedApp(
        [
            (r'/events', EventSource),
            (r'/(.*)', web.StaticFileHandler, {"path": static_dir, "default_filename": "index.html"})
        ],
        debug=env is 'DEV'
    )

    app.listen(int(port))
    print('Application is listening at port {}'.format(port))
    def safe_shutdown():
        print('Server has been shutdown. Bye!')

        IOLoop.current().stop()
        app.stop()

    signal.signal(signal.SIGINT, lambda a, b: safe_shutdown())
    signal.signal(signal.SIGTERM, lambda a, b: safe_shutdown())
    IOLoop.current().start()
