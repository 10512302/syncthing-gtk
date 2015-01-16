#!/usr/bin/env python2
"""
Syncthing-GTK - tools

Wrapper around GTKBuilder. Allows using conditional (<IF>) tags in
glade files.

Usage:
	- Crete instance
	- Enable conditions (enable_condition call)
	- Call add_from_file or add_from_string method
	- Continue as usual

Added tags:
	<IF condition="c"> ... </IF>
		If condition is met, tag is replaced with its child tags
		If condition is not met, tag and all child tags are removed
	<IF condition="c"> ... <ELSE> ... </ELSE></IF>
		If condition is met, tag is replaced with its child tags and
		ELSE tag is removed including its children.
		If condition is not met, tag is replaced with children of ELSE
		tag. All other children, including ELSE tag are removed.
	<COPYOBJECT id="i" />
		Searchs for OBJECT tag with same id and replaces COPYOBJECT tag
		with its copy.

"""

from __future__ import unicode_literals
from gi.repository import Gtk
from xml.dom import minidom
import logging
log = logging.getLogger("UIBuilder")

class UIBuilder(Gtk.Builder):
	def __init__(self):
		Gtk.Builder.__init__(self)
		self.conditions = set([])
		self.icon_paths = []
		self.xml = None
	
	def add_from_file(self, filename):
		""" Builds UI from file """
		log.debug("Loading glade file %s", filename)
		self.add_from_string(file(filename, "r").read())
	
	def add_from_string(self, string):
		""" Builds UI from string """
		self.xml = minidom.parseString(string)
		self._build()
	
	def add_from_resource(self, *a):
		raise RuntimeError("add_from_resource is not supported")
	
	def enable_condition(self, *conds):
		""" Enables condition. Conditions are case-insensitive """
		for c in conds:
			log.debug("Enabled: %s", c)
			self.conditions.add(c)
	
	def disable_condition(self, *conds):
		""" Disables condition. Conditions are case-insensitive """
		for c in conds:
			log.debug("Disabled: %s", c)
			self.conditions.remove(c)
	
	def condition_met(self, cond):
		"""
		Returns True if condition is met. Empty condition is True.
		Spaces at begining or end of expressions are stripped.
		
		Supports simple |, & and !
		operators, but no parenthesis.
		(I just hope I'd never have to use them)
		"""
		if "|" in cond:
			for sub in cond.split("|", 1):
				if self.condition_met(sub):
					return True
			return False
		if "&" in cond:
			for sub in cond.split("&", 1):
				if not self.condition_met(sub):
					return False
			return True
		if cond.strip().startswith("!"):
			return not self.condition_met(cond.strip()[1:])
		return cond.strip() in self.conditions
	
	def replace_icon_path(self, prefix, replace_with):
		"""
		All path replaceaments defined using this method are applied
		by _build method on anything that remotely resembles icon path.
		"""
		if not prefix.endswith("/"): prefix = "%s/" % (prefix,)
		if not replace_with.endswith("/"): replace_with = "%s/" % (replace_with,)
		self.icon_paths.append((prefix, replace_with))
	
	def _build(self):
		"""
		Fun part starts here. Recursively walks through entire DOM tree,
		removes all <IF> tags replacing them with child nodes if when
		condition is met and fixes icon paths, if required.
		"""
		log.debug("Enabled conditions: %s", self.conditions)
		self._objects_n_icons(self.xml.documentElement)
		self._find_conditions(self.xml.documentElement)
		# Now this will convert parsed DOM tree back to XML and fed it
		# to Gtk.Builder XML parser.
		# God probably kills kitten every time when method is called...
		file("output.glade", "w").write(self.xml.toxml("utf-8"))
		Gtk.Builder.add_from_string(self, self.xml.toxml("utf-8"))
	
	def _objects_n_icons(self, node):
		"""
		1st recursive stage for _build. Fixes icon paths
		and copies objects.
		"""
		for child in node.childNodes:
			if child.nodeType == child.ELEMENT_NODE:
				if child.tagName.lower() == "copyobject":
					id = child.getAttribute("id")
					if id == "":
						log.warn("COPYOBJECT tag without id")
					else:
						obj = search_for_id(self.xml, id)
						cpy = obj.cloneNode(True)
						child.parentNode.appendChild(cpy)
						child.parentNode.insertBefore(cpy, child)
						child.parentNode.removeChild(child)
						self._objects_n_icons(cpy)
				else:
					self._objects_n_icons(child)
					if child.tagName.lower() == "property":
						if child.getAttribute("name") == "pixbuf":
							# GtkImage, pixbuf path
							self._check_icon_path(child)
						elif child.getAttribute("name") == "icon":
							# window or dialog, icon path
							self._check_icon_path(child)
	
	def _find_conditions(self, node):
		""" Recursive part for _build - <IF> tags """
		for child in node.childNodes:
			if child.nodeType == child.ELEMENT_NODE:
				self._find_conditions(child)
				if child.tagName.lower() == "if":
					self._solve_if_element(child)
				elif child.getAttribute("if") != "":
					condition = child.getAttribute("if")
					if not self.condition_met(condition):
						log.debug("Removed '%s' by attribute: %s", child.tagName, condition)
						node.removeChild(child)
					else:
						child.removeAttribute("if")
	
	def _solve_if_element(self, element):
		"""
		Reads "condition" attribute and decides if condition is met
		Conditions are case-insensitive
		"""
		condition = element.getAttribute("condition").lower().strip()
		if self.condition_met(condition):
			# Merge child nodes in place of this IF element
			# Remove ELSE elements, if any
			log.debug("Allowed node %s", condition)
			for elseem in getElementsByTagNameCI(element, "else"):
				element.removeChild(elseem)
			merge_with_parent(element, element)
		else:
			# Remove this element, but merge ELSE elemnets, if any
			log.debug("Removed node %s", condition)
			for elseem in getElementsByTagNameCI(element, "else"):
				merge_with_parent(elseem, element)
			element.parentNode.removeChild(element)
	
	def _check_icon_path(self, element):
		def replace(path):
			"""
			If specified path begins with one of replaceament prefixes,
			returns path with modified prefix.
			"""
			for prefix, replace_with in self.icon_paths:
				if path.startswith(prefix):
					return "%s%s" % (replace_with, path[len(prefix):])
			return path
		
		for n in element.childNodes:
			if n.nodeType == n.TEXT_NODE:
				n.data = replace(n.data)
		return
	

def getElementsByTagNameCI(node, tagname):
	"""
	Returns all elements with matching tag; Compares in
	case-insensitive way.
	"""
	tagname = tagname.lower()
	return [ child for child in node.childNodes if 
			(child.nodeType == child.ELEMENT_NODE and
			child.tagName.lower() == tagname)
		]

def merge_with_parent(element, insert_before):
	""" Merges child nodes with parent node """
	for child in element.childNodes:
		if child.nodeType == child.ELEMENT_NODE:
			element.removeChild(child)
			insert_before.parentNode.appendChild(child)
			insert_before.parentNode.insertBefore(child, insert_before)
	element.parentNode.removeChild(element)

def search_for_id(element, id):
	"""
	Recursively search for object with specified id. Returns found
	object or None if there is no such object.
	"""
	for child in element.childNodes:
		if child.nodeType == child.ELEMENT_NODE:
			if id == child.getAttribute("id"):
				return child
			r = search_for_id(child, id)
			if not r is None:
				return r
	return None
