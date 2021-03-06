# vim:set et!:

import os
import xml.etree.ElementTree
from StringIO import StringIO
from sicekit.wiki.exportimport.wikiutil import WikiUtil, XMLNS, APIRequest

class Importer(object):
	"""The Importer ill import all articles and files from
	configuration.datapath into the configured wiki."""

	def __init__(self, configuration, wiki):
		self.configuration = configuration
		self.wikiutil = WikiUtil(wiki)
		self.wiki = self.wikiutil.wiki # WikiUtil modifies wiki

	def _buildPageListPerDir(self, pagelist, dirname, fnames):
		for fname in fnames:
			path = os.path.join(dirname, fname)
			if os.path.isfile(path) and path.endswith('.xml'):
				print "I: Considering file %s." % path
				pagelist.append(self.readDumpFile(path))

	def _buildPageList(self):
		pagelist = []
		os.path.walk(self.configuration.datapath, self._buildPageListPerDir, pagelist)
		return pagelist

	def _buildFileListPerDir(self, filelist, dirname, fnames):
		for fname in fnames:
			path = os.path.join(dirname, fname)
			if os.path.isfile(path) and path.endswith('.sha1'):
				path = path.rpartition('.')[0]
				print "I: Considering file %s." % path
				filelist.append(path)

	def _buildFileList(self):
		filelist = []
		os.path.walk(os.path.join(self.configuration.datapath, 'File'), self._buildFileListPerDir, filelist)
		return filelist

	def readDumpFile(self, path):
		xmlEl = self.wikiutil.readXmlFromFile(path)
		title = xmlEl.find(XMLNS+u'page/'+XMLNS+u'title').text
		revision = xmlEl.find(XMLNS+u'page/'+XMLNS+u'revision')
		revision.find(XMLNS+u'timestamp').text = self.wikiutil.buildWikiTimestampNow()
		revision.find(XMLNS+u'id').text = '1'

		io = StringIO(xml.etree.ElementTree.tostring(xmlEl))
		io.name = "import.xml"

		return {u'title': title, u'io':io, u'xmldoc': xmlEl}

	def importPage(self, page):
		"""Runs an XML import for page "page"."""
		title = page[u'title']
		print "I: Importing page %s." % title

		oldpage = self.wikiutil.retrievePageExportXml(title)
		if oldpage is not None:
			oldtext = self.wikiutil.getPageTextFromXml(oldpage)
			newtext = self.wikiutil.getPageTextFromXml(page[u'xmldoc'])
			if oldtext == newtext:
				print "I: Skipping, no changes."
				return

		# fetch import token
		params = {'action':'query', 'prop':'info', 'intoken':'import', 'titles':title}
		request = APIRequest(self.wiki, params)
		result = request.query()['query']
		if u'warnings' in result.keys():
			print 'W: Wiki gave warning: ' + result[u'warnings'][u'info'][u'*']
		pages = result['pages']
		importtoken = pages[pages.keys()[0]]['importtoken']

		# now post the page
		params = {'action':'import', 'token':importtoken}
		request = APIRequest(self.wiki, params)
		request.setMultipart()
		request.changeParam('xml', page[u'io'])
		result = request.query()

		if result[u'import'][0][u'revisions'] != 1:
			print "E: Page import failed. Wiki said:", result
			return 1

		self.pagecount = self.pagecount + 1
		self.changecount = self.changecount + result[u'import'][0][u'revisions']

	def importFile(self, path):
		"""Uploads a file from "path" to the wiki, first checking against the
		stored sha1sums.
		"""
		prefix = os.path.commonprefix([path, os.path.join(self.configuration.datapath, 'File')])
		title = path[len(prefix)+1:]
		print "I: Importing image %s." % title

		# get new sha1
		new_sha1sum = file(path + '.sha1', 'r').read(40)
		new_sha1dum = new_sha1sum.strip('\r\n ')

		# get old sha1 from wiki, don't import if they match
		old_image = self.wikiutil.retrieveImageInfo('File:%s' % title)
		if not old_image.has_key('missing'):
			old_sha1sum = old_image['imageinfo'][0][u'sha1']
			if old_sha1sum == new_sha1sum:
				print "I: Skipping, no changes."
				return

		# fetch import token
		params = {'action':'query', 'prop':'info', 'intoken':'edit', 'titles':'File:%s'%title}
		request = APIRequest(self.wiki, params)
		result = request.query()['query']
		if u'warnings' in result.keys():
			print 'W: Wiki gave warning: ' + result[u'warnings'][u'info'][u'*']
		pages = result['pages']
		token = pages[pages.keys()[0]]['edittoken']

		# get us the file object, so we can attach it to our request
		f = file(path, 'r')
		# now post the real upload request
		params = {'action':'upload', 'filename':title, 'token':token, 'comment':'Origin-SICEKIT', 'ignorewarnings':True}
		request = APIRequest(self.wiki, params)
		request.setMultipart()
		request.changeParam('file', f)
		result = request.query()
		f.close()

		if result[u'upload'][u'result'] != 'Success':
			print "E: Page import failed. Wiki said:", result
			return 1

		self.pagecount = self.pagecount + 1
		self.changecount = self.changecount + 1

	def run(self):
		"""Main entry point for the Importer."""
		self.pagecount = 0
		self.changecount = 0

		print "I: Looking for pages to import in %s." % self.configuration.datapath
		pagelist = self._buildPageList()
		print "I: Now importing pages."
		map(self.importPage, pagelist)

		print "I: Looking for images to import in %s." % self.configuration.datapath
		filelist = self._buildFileList()
		print "I: Now importing images."
		map(self.importFile, filelist)

		print "I: Imported %d pages, resulting in %d changes." % (self.pagecount, self.changecount)
		return 0
