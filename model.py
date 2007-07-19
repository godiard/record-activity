#!/usr/bin/env python

import urllib
import string
import fnmatch
import os
import random
import cairo
import gtk
import pygtk
pygtk.require('2.0')
import shutil

import math
import gtk.gdk
import sugar.env
import random
import time
import gobject
import xml.dom.minidom
from xml.dom.minidom import getDOMImplementation
from xml.dom.minidom import parse

from recorded import Recorded
from color import Color

import _camera

class Model:
	def __init__( self, pca ):
		self.ca = pca
		self.setConstants()
		self.journalIndex = os.path.join(self.ca.journalPath, 'camera_index.xml')
		self.mediaHashs = {}
		self.fillMediaHash( self.journalIndex )


	def fillMediaHash( self, index ):
		self.mediaHashs[self.TYPE_PHOTO] = []
		self.mediaHashs[self.TYPE_VIDEO] = []
		if (os.path.exists(index)):
			doc = parse( os.path.abspath(index) )
			photos = doc.documentElement.getElementsByTagName('photo')
			for each in photos:
				self.loadMedia( each, self.mediaHashs[self.TYPE_PHOTO] )

			videos = doc.documentElement.getElementsByTagName('video')
			for each in videos:
				self.loadMedia( each, self.mediaHashs[self.TYPE_VIDEO] )

	def loadMedia( self, el, hash ):
		recd = Recorded()

		recd.type = int(el.getAttribute('type'))
		recd.name = el.getAttribute('name')
		recd.time = int(el.getAttribute('time'))
		recd.photographer = el.getAttribute('photographer')
		recd.mediaFilename = el.getAttribute('mediaFilename')
		recd.thumbFilename = el.getAttribute('thumbFilename')
		colorStrokeHex = el.getAttribute('colorStroke')
		colorStroke = Color()
		colorStroke.init_hex( colorStrokeHex )
		recd.colorStroke = colorStroke
		colorFillHex = el.getAttribute('colorFill')
		colorFill = Color()
		colorFill.init_hex( colorFillHex )
		recd.colorFill = colorFill
		recd.buddy = (el.getAttribute('buddy') == "True")
		recd.hashKey = el.getAttribute('hashKey')

		hash.append( recd )

	def saveMedia( self, el, recd, type ):
		el.setAttribute("type", str(type))
		el.setAttribute("name", recd.name)
		el.setAttribute("time", str(recd.time))
		el.setAttribute("photographer", recd.photographer)
		el.setAttribute("mediaFilename", recd.mediaFilename)
		el.setAttribute("thumbFilename", recd.thumbFilename)
		el.setAttribute("colorStroke", str(recd.colorStroke.hex) )
		el.setAttribute("colorFill", str(recd.colorFill.hex) )
		el.setAttribute("hashKey", str(recd.hashKey))
		el.setAttribute("buddy", str(recd.buddy))


	def selectLatestThumbs( self, type ):
		p_mx = len(self.mediaHashs[type])
		p_mn = max(p_mx-self.ca.ui.numThumbs, 0)
		gobject.idle_add(self.setupThumbs, type, p_mn, p_mx)


	def isVideoMode( self ):
		return self.MODE == self.MODE_VIDEO


	def isPhotoMode( self ):
		return self.MODE == self.MODE_PHOTO


	def setupThumbs( self, type, mn, mx ):

		if (not type == self.MODE):
			return

		self.setUpdating( True )

		hash = self.mediaHashs[type]

		#don't load more than you possibly need by accident
		if (mx>mn+self.ca.ui.numThumbs):
			mx = mn+self.ca.ui.numThumbs
		mx = min( mx, len(hash) )

		if (mn<0):
			mn = 0

		if (mx == mn):
			mn = mx-self.ca.ui.numThumbs

		if (mn<0):
			mn = 0

		#
		#	UI
		#
		#at which # do the left and right buttons begin?
		left = -1
		rigt = -1
		if (mn>0):
			left = max(0, mn-self.ca.ui.numThumbs)
		rigt = mx
		if (mx>=len(hash)):
			rigt = -1

		#get these from the hash to send over
		addToTray = []
		for i in range (mn, mx):
			addToTray.append( hash[i] )

		self.ca.ui.updateThumbs( addToTray, left, mn, rigt  )
		self.setUpdating( False )


	def getHash( self ):
		type = -1
		if (self.ca.m.MODE == self.ca.m.MODE_PHOTO):
			type = self.ca.m.TYPE_PHOTO
		if (self.ca.m.MODE == self.ca.m.MODE_VIDEO):
			type = self.ca.m.TYPE_VIDEO

		if (type != -1):
			return self.mediaHashs[type]
		else:
			return None


	def doShutter( self ):
		if (self.UPDATING):
			return

		if (self.MODE == self.MODE_PHOTO):
			self.startTakingPhoto()
		elif (self.MODE == self.MODE_VIDEO):
			if (not self.RECORDING):
				self.startRecordingVideo()
			else:
				self.stopRecordingVideo()


	def startRecordingVideo( self ):
		self.setUpdating( True )
		self.RECORDING = True

		self.ca.ui.recordVideo()

		self.setUpdating( False )


	def setUpdating( self, upd ):
		self.UPDATING = upd
		self.ca.ui.updateShutterButton()


	def stopRecordingVideo( self ):
		self.setUpdating( True )

		self.ca.ui.hideLiveWindows()
		self.ca.ui.hidePlayWindows()

		self.ca.glive.stopRecordingVideo()


	def saveVideo( self, pixbuf, tempPath ):
		recd = self.createNewRecorded( self.TYPE_VIDEO )

		oggPath = os.path.join(self.ca.journalPath, recd.mediaFilename)
		thumbPath = os.path.join(self.ca.journalPath, recd.thumbFilename)

		#todo: dynamic creation of this ratio
		thumbImg = self.generateThumbnail(pixbuf, float(.66875) )
		thumbImg.write_to_png(thumbPath)
		#thumb = pixbuf.scale_simple( self._thuPho.tw, self._thuPho.th, gtk.gdk.INTERP_BILINEAR )
		#thumb.save( thumbpath, "jpeg", {"quality":"85"} )
		shutil.move(tempPath, oggPath)

		videoHash = self.mediaHashs[self.TYPE_VIDEO]
		videoHash.append( recd )
		self.updateMediaIndex()
		self.thumbAdded( self.TYPE_VIDEO )

		#resume live video from the camera (if the activity is active)
		if (self.ca.ACTIVE):
			self.ca.ui.updateVideoComponents()
			self.ca.glive.play()

		self.RECORDING = False

	def stoppedRecordingVideo( self ):
		self.setUpdating( False )


	def startTakingPhoto( self ):
		self.setUpdating( True )
		self.ca.glive.takePhoto()


	def savePhoto( self, pixbuf ):
		recd = self.createNewRecorded( self.TYPE_PHOTO )

		imgpath = os.path.join(self.ca.journalPath, recd.mediaFilename)
		pixbuf.save( imgpath, "jpeg" )

		thumbpath = os.path.join(self.ca.journalPath, recd.thumbFilename)
		#todo: generate this dynamically
		thumbImg = self.generateThumbnail(pixbuf, float(0.1671875))
		thumbImg.write_to_png(thumbpath)
		#todo: use this code...?
		#thumb = pixbuf.scale_simple( self._thuPho.tw, self._thuPho.th, gtk.gdk.INTERP_BILINEAR )
		#thumb.save( thumbpath, "jpeg", {"quality":"85"} )

		self.addPhoto( recd )

		#hey, i just took a cool picture!  let me show you!
		if (self.ca.meshClient != None):
			#md5?
			self.ca.meshClient.notifyBudsOfNewPhoto( recd )


	def addPhoto( self, recd ):
		self.mediaHashs[self.TYPE_PHOTO].append( recd )
		#todo: sort on time-taken
		#save index
		self.updateMediaIndex()
		#updateUi
		self.thumbAdded(self.TYPE_PHOTO)

		self.setUpdating( False )


	#assign a better name here (name_0.jpg)
	def createNewRecorded( self, type ):
		recd = Recorded()

		nowtime = int(time.time())
		nowtime_s = str(nowtime)
		recd.time = nowtime

		recd.type = type
		if (type == self.TYPE_PHOTO):
			nowtime_fn = nowtime_s + ".jpg"
			recd.mediaFilename = nowtime_fn
		if (type == self.TYPE_VIDEO):
			nowtime_fn = nowtime_s + ".ogg"
			recd.mediaFilename = nowtime_fn

		thumb_fn = nowtime_s + "_thumb.jpg"
		recd.thumbFilename = thumb_fn

		recd.photographer = self.ca.nickName
		recd.name = recd.mediaFilename

		recd.colorStroke = self.ca.ui.colorStroke
		recd.colorFill = self.ca.ui.colorFill
		recd.hashKey = self.ca.hashedKey

		return recd


	#outdated?
	def generateThumbnail( self, pixbuf, scale ):
#		#need to generate thumbnail version here
		thumbImg = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.ca.ui.tw, self.ca.ui.th)
		tctx = cairo.Context(thumbImg)
		img = _camera.cairo_surface_from_gdk_pixbuf(pixbuf)

		tctx.scale(scale, scale)
		tctx.set_source_surface(img, 0, 0)
		tctx.paint()
		return thumbImg


	def deleteRecorded( self, recd, mn ):
		#clear the index
		hash = self.mediaHashs[recd.type]
		index = hash.index(recd)
		hash.remove( recd )
		self.updateMediaIndex( )
		#clear transients
		recd.thumb = None
		recd.media = None

		#remove files from the filesystem
		mediaFile = os.path.join(self.ca.journalPath, recd.mediaFilename)
		if (recd.buddy):
			mediaFile = os.path.join(self.ca.journalPath, "buddies", recd.thumbFilename)
		if (os.path.exists(mediaFile)):
			os.remove(mediaFile)

		thumbFile = os.path.join(self.ca.journalPath, recd.thumbFilename)
		if (recd.buddy):
			thumbFile = os.path.join(self.ca.journalPath, "buddies", recd.thumbFilename)
		if (os.path.exists(thumbFile)):
			os.remove(thumbFile)

		if (not recd.buddy):
			self.ca.meshClient.notifyBudsofDeleteMedia( recd )

		self.setupThumbs(recd.type, mn, mn+self.ca.ui.numThumbs)


	def deleteBuddyMedia( self, hashKey, time, type ):
		if (type == self.TYPE_PHOTO or type == self.TYPE_VIDEO):
			hash = self.mediaHashs[type]
			for recd in hash:
				if ((recd.hashKey == hashKey) and (recd.time == time)):
					#todo: pass in -1 since we don't know where it is (or we should find out)
					self.deleteRecorded( recd, 0 )
					#todo: remove it in the main ui if showing it


	#todo: update photo index to point to the "buddies"
	def updateMediaIndex( self ):
		#delete all old htmls
		files = os.listdir(self.ca.journalPath)
		for file in files:
			if (len(file) > 5):
				if ("html" == file[len(file)-4:]):
					html = os.path.join(self.ca.journalPath, file)
					os.remove(html)

		impl = getDOMImplementation()
		album = impl.createDocument(None, "album", None)
		root = album.documentElement
		photoHash = self.mediaHashs[self.TYPE_PHOTO]
		for i in range (0, len(photoHash)):
			recd = photoHash[i]

			photo = album.createElement('photo')
			root.appendChild(photo)
			self.saveMedia(photo, recd, self.TYPE_PHOTO)

			htmlDoc = impl.createDocument(None, "html", None)
			html = htmlDoc.documentElement
			head = htmlDoc.createElement('head')
			html.appendChild(head)
			title = htmlDoc.createElement('title')
			head.appendChild(title)
			titleText = htmlDoc.createTextNode( "Your Photos" )
			title.appendChild(titleText)
			body = htmlDoc.createElement('body')
			html.appendChild(body)
			center = htmlDoc.createElement('center')
			body.appendChild(center)
			ahref = htmlDoc.createElement('a')
			center.appendChild(ahref)

			if (len(photoHash)>0):
				nextRecd = photoHash[0]
				if (i < len(photoHash)-1):
					nextRecd = photoHash[i+1]
				#todo: more specific, per kid?
				nextHtml = os.path.join(self.ca.journalPath, str(nextRecd.time)+".html")
				ahref.setAttribute('href', os.path.abspath(nextHtml))

			img = htmlDoc.createElement('img')
			img.setAttribute("width", "320")
			img.setAttribute("height", "240")
			ahref.appendChild(img)
			img.setAttribute('src', recd.mediaFilename)
			if (i == 0):
				f = open(os.path.join(self.ca.journalPath, "index.html"), 'w')
				htmlDoc.writexml(f)
				f.close()
			else:
				f = open(os.path.join(self.ca.journalPath, str(recd.time)+".html"), 'w')
				htmlDoc.writexml(f)
				f.close()

		videoHash = self.mediaHashs[self.TYPE_VIDEO]
		for i in range (0, len(videoHash)):
			recd = videoHash[i]

			video = album.createElement('video')
			root.appendChild(video)
			self.saveMedia(video, recd, self.TYPE_VIDEO)

		f = open( self.journalIndex, 'w')
		album.writexml(f)
		f.close()


	#todo: if you are not at the end of the list, do we want to force you to the end?
	def thumbAdded( self, type ):
		mx = len(self.mediaHashs[type])
		mn = max(mx-self.ca.ui.numThumbs, 0)
		self.setupThumbs(type, mn, mx)


	def doVideoMode( self ):
		if (self.MODE == self.MODE_VIDEO):
			return

		self.setUpdating(True)
		#assign your new mode
		self.MODE = self.MODE_VIDEO
		self.selectLatestThumbs(self.TYPE_VIDEO)


		self.ca.ui.updateModeChange()
		self.setUpdating(False)


	def doPhotoMode( self ):
		if (self.MODE == self.MODE_PHOTO):
			return

		self.setUpdating(True)
		#assign your new mode
		self.MODE = self.MODE_PHOTO
		self.selectLatestThumbs(self.TYPE_PHOTO)

		self.ca.ui.updateModeChange()
		self.setUpdating(False)


	def setConstants( self ):
		#pics or vids?
		self.MODE_PHOTO = 0
		self.MODE_VIDEO = 1
		self.MODE = self.MODE_PHOTO

		self.TYPE_PHOTO = 0
		self.TYPE_VIDEO = 1

		self.UPDATING = True
		self.RECORDING = False