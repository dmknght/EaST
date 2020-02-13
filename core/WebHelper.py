import mimetypes
import os
import time
import cookielib
import urllib2
import urllib
import threading
try:
    from BaseHTTPServer import HTTPServer
except ModuleNotFoundError:
    import http.server as HTTPServer
try:
    from BaseHTTPServer import BaseHTTPRequestHandler
except ModuleNotFoundError:
    from http.server import BaseHTTPRequestHandler

import shutil


class FormPoster:
    def __init__(self):
        self.BOUNDARY = '----------ThIs_Is_tHe_saLteD_bouNdaRY_$'
        self.fields = []
        self.files = []

    def post(self, target, additional_headers={}):
        """
        Post fields and files to an http target as multipart/form-data.
        additional_headers can add new headers or overwrite existing.
        Return the server's response page.
        """
        request = urllib2.Request(target)
        request.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:41.0) Gecko/20100101 Firefox/41.0')
        content_type, body = self._encode_multipart_formdata()
        request.add_header('Content-Type', content_type)
        request.add_header('Content-Length', str(len(body)))
        if type(additional_headers) is dict:
            for key in additional_headers:
                request.add_header(key, additional_headers[key])
        request.add_data(body)
        return request

    def _encode_multipart_formdata(self):
        """
        fields is a sequence of (name, value) elements for regular form fields.
        files is a sequence of (name, filename, value) elements for data to be uploaded as files
        Return (content_type, body)
        """
        CRLF = '\r\n'
        L = []
        for (key, value) in self.fields:
            L.append('--' + self.BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"' % key)
            L.append('')
            L.append(value)
        for (key, filename, value, content_type) in self.files:
            L.append('--' + self.BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
            if content_type:
                L.append('Content-Type: %s' % content_type)
            L.append('')
            L.append(value)
        L.append('--' + self.BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % self.BOUNDARY
        return content_type, body

    def add_field(self, key, value):
        self.fields.append((key, value))

    def add_file(self, key, filename, file, is_path=True, content_type=''):
        """Add file entry to a form.
        If 'is_path' - True 'file' must be path to file
        If 'is_path' - False 'file' - is text content
        """
        file = open(file, 'rb').read() if is_path else file
        self.files.append((key, filename, file, content_type))

class NoRedirection(urllib2.HTTPErrorProcessor):
    """ Creates no redirection handler
    For example:
    no_redir = NoRedirection()
    print no_redir.open_http_address("http://habr.ru").geturl()
    """

    def http_response(self, request, response):
        return response

    def open_http_address(self, address):
        cj = cookielib.CookieJar()
        opener = urllib2.build_opener(NoRedirection, urllib2.HTTPCookieProcessor(cj))
        response = opener.open(address)
        return response

    https_response = http_response

def wordpress_auth(host, username, password):
    """Returns opener and cookie
        Example:
             opener, cookie = wordpress_auth('http://www.wordpresssite.com', 'guest', 'guest')
             res = opener.open('http://www.wordpresssite.com/wp-admin/profile.php')
    """
    cookie = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie))
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; rv:14.0) Gecko/20100101 Firefox/14.0.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-ru,ru;q=0.8,en-us;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'DNT': '1'
    }
    payload = {
        'log': username,
        'pwd': password,
        'wp-submit': 'Log+In',
        'rememberme': 'forever',
        'redirect_to': host+'wp-admin',
        'testcookie': '1'
    }
    if host[-1] != '/' and host[-1] != '\\':
        host += '/'
    login_url = host + 'wp-login.php'
    payload = urllib.urlencode(payload)

    httpReq = urllib2.Request(login_url, payload, headers)
    page = opener.open(httpReq)
    return opener, cookie


class SimpleWebServerHandler(BaseHTTPRequestHandler):
    CONTENT = ""
    def do_GET(self):
        self.send_response(200)
        if 'admin.php' in self.path:
            self.wfile.write(self.CONTENT)
        self.wfile.write('')


class AdavancedHttpServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.path = os.path.normpath(self.path)
        if self.path in self.server.files_for_share:
            self.send_response(200)
            local_file_path = self.server.files_for_share.get(self.path)
            mime = mimetypes.guess_type(local_file_path)
            if not mime:
                mime = "plain/text"
                # self.download_file(local_file_path)
                # return
            self.send_header('Content-Type', mime[0])
            for header, value in self.server.custom_headers.items():
                self.send_header(header, value)
            self.end_headers()
            with open(local_file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, "File not found")

    def download_file(self, filename):
        with open(filename, 'rb') as f:
            self.send_response(200)
            self.send_header("Content-Type", 'application/octet-stream')
            self.send_header("Content-Disposition", 'attachment; filename="{}"'.format(os.path.basename(filename)))
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs.st_size))
            self.end_headers()
            shutil.copyfileobj(f, self.wfile)


class SimpleWebServer:
    def __init__(self, host, port):
        """Simple http server. You can add local files to show them in web.
        Example:
            server = SimpleWebServer('localhost', 8080)
            server.add_file_for_share("new1123.html", "<h1>HTML FILE TEST</h1>")
            server.add_folder_for_share("E:\\work\\EaST")
            server.add_header("CustomHeader", "CustomValue")
            server.start_serve()
            time.sleep(10)
            server.stop_serve() # Kill the server
        """
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None
        self.temp_dir = ""
        self.headers = {}
        self.files = {}
        self.create_temp_folder()

    def set_headers(self, headers={}):
        self.headers = headers

    def add_header(self, key, value):
        self.headers[key] = value

    def create_temp_folder(self):
        try:
            self.temp_dir = os.path.join(os.getcwd(), "tmp", "Webserver"+time.strftime('%Y%m%d%H%M%S', time.gmtime()))
            os.makedirs(self.temp_dir)
        except Exception as e:
            self.temp_dir = ""
            print(str(e))

    def add_file_for_share(self, filename, content, server_path=''):
        """
        Add local file for share it to the web
        :param filename:(string) Filename
        :param content:(string) File content
        :param server_path:(string) '/' - means server root
        """
        if server_path == "/" or server_path == "\\":
            server_path = ""
        if server_path.startswith("/") or server_path.startswith("\\"):
            server_path = server_path[1:]
        full_server_filepath = os.path.join(server_path, filename)
        path = os.path.join(self.temp_dir, server_path)
        if not os.path.exists(path):
            os.makedirs(path)
        with open(os.path.join(self.temp_dir, full_server_filepath), 'wb') as f:
            f.write(content)
        local_path = os.path.normpath(os.path.join(self.temp_dir, full_server_filepath))
        full_server_filepath = os.path.normpath("/" + full_server_filepath)
        self.files[full_server_filepath] = local_path

    def add_folder_for_share(self, local_path):
        """
        Add all files from chosen folder and subfolders
        :param local_path: (string) Local folder path
        """
        local_path = os.path.normpath(local_path)
        for path, dirs, files in os.walk(local_path):
            for file in files:
                local_file_path = os.path.join(path, file)
                server_file_path = local_file_path.replace(local_path, '')
                self.files[server_file_path] = local_file_path

    def start_serve(self):
        self.stop_serve()
        try:
            self.httpd = HTTPServer((self.host, self.port), AdavancedHttpServerHandler)
            setattr(self.httpd, "files_for_share", self.files)
            setattr(self.httpd, "custom_headers", self.headers)
            self.thread = threading.Thread(target=self.httpd.serve_forever, args=())
            self.thread.start()
            return (True, "OK")
        except Exception as e:
            return (False, e)

    def start_with_content(self, content):
        self.stop_serve()
        try:
            self.httpd = HTTPServer((self.host, self.port), SimpleWebServerHandler)
            SimpleWebServerHandler.CONTENT = content
            self.thread = threading.Thread(target=self.httpd.serve_forever, args=())
            self.thread.start()
            return (True, "OK")
        except Exception as e:
            return (False, e)

    def stop_serve(self):
        if self.httpd:
            self.httpd.shutdown()
        if self.thread:
            self.thread.join()

if __name__ == '__main__':
    pass
