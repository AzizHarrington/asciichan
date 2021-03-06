import os
import urllib2
from xml.dom import minidom

import webapp2
import jinja2
import logging
import time

from google.appengine.ext import db
from google.appengine.api import memcache


GMAPS_URL = "https://maps.googleapis.com/maps/api/staticmap?size=380x263&sensor=false&"

IP_URL = "http://api.hostip.info/?ip="

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)


class Handler(webapp2.RequestHandler):

    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))


def gmaps_img(points):
    markers = '&'.join('markers=%s,%s' % (p.lat, p.lon)
                       for p in points)
    return GMAPS_URL + markers


def get_coords(ip):
    ip = '67.175.72.40'
    url = IP_URL + ip
    content = None
    try:
        content = urllib2.urlopen(url).read()
    except urllib2.URLError:
        return

    if content:
        d = minidom.parseString(content)
        coords = d.getElementsByTagName("gml:coordinates")
        if coords and coords[0].childNodes[0].nodeValue:
            lon, lat = coords[0].childNodes[0].nodeValue.split(',')
            return db.GeoPt(lat, lon)


class Art(db.Model):

    title = db.StringProperty(required=True)
    art = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    coords = db.GeoPtProperty()


def top_arts(update=False):
    key = 'top'
    arts = memcache.get(key)
    if arts is None or update:
        logging.error("DB QUERY")
        arts = db.GqlQuery("SELECT * FROM Art ORDER BY created DESC")
        # prevent the running of multiple queries
        arts = list(arts)
        memcache.set(key, arts)
    return arts


class MainPage(Handler):

    def render_front(self, title="", art="", error=""):
        arts = top_arts()

        # find which arts have coords
        points = filter(None, (a.coords for a in arts))

        # if we have any arts coords, make an image url
        img_url = None
        if points:
            img_url = gmaps_img(points)

        # display the image url, pass into template
        self.render("ascii_template.html",
                    title=title,
                    art=art,
                    error=error,
                    arts=arts,
                    img_url=img_url)

    def get(self):
        return self.render_front()

    def post(self):
        title = self.request.get("title")
        art = self.request.get("art")

        if title and art:
            p = Art(title=title, art=art)
            coords = get_coords(self.request.remote_addr)
            # if we have coordinates, add them to the Art
            if coords:
                p.coords = coords

            p.put()
            # rerun the query and update the cache
            time.sleep(0.1)  # buffer against replication lag
            top_arts(True)

            self.redirect("/")
        else:
            error = "we need both a title and some artwork!"
            self.render_front(title, art, error)


app = webapp2.WSGIApplication([('/', MainPage)], debug=True)