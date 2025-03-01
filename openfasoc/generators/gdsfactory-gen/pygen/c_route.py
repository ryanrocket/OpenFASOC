from gdsfactory.cell import cell
from gdsfactory.component import Component
from gdsfactory.port import Port
from .pdk.mappedpdk import MappedPDK
from typing import Optional, Union
from math import isclose
from .via_gen import via_stack
from gdsfactory.routing.route_quad import route_quad
from gdsfactory.components.rectangle import rectangle
from .pdk.util.comp_utils import evaluate_bbox
from .pdk.util.port_utils import add_ports_perimeter, rename_ports_by_orientation, rename_ports_by_list, print_ports, set_port_width, set_port_orientation, get_orientation
from pydantic import validate_arguments


@validate_arguments
def __fill_empty_viastack__macro(pdk: MappedPDK, glayer: str, size: tuple[float,float]) -> Component:
	"""returns a rectangle with ports that pretend to be viastack ports"""
	comp = rectangle(size=size,layer=pdk.get_glayer(glayer),centered=True)
	return rename_ports_by_orientation(rename_ports_by_list(comp,replace_list=[("e","top_met_")])).flatten()

@cell
def c_route(
	pdk: MappedPDK, 
	edge1: Port, 
	edge2: Port, 
	extension: Optional[float]=0.5, 
	width1: Optional[float] = None, 
	width2: Optional[float] = None,
	cwidth: Optional[float] = None,
	e1glayer: Optional[str] = None, 
	e2glayer: Optional[str] = None, 
	cglayer: Optional[str] = None, 
	viaoffset: Optional[Union[bool,tuple[Optional[bool],Optional[bool]]]]=(True,True),
	fullbottom: Optional[bool] = False
) -> Component:
	"""creates a C shaped route between two Ports.
	
	edge1--|
	       |
	edge2--|
	
	REQUIRES: ports be parralel vertical or horizontal edges
	****NOTE: does no drc error checking (creates a dumb route)
	args:
	pdk = pdk to use
	edge1 = first port
	edge2 = second port
	width1 = optional will default to edge1 width if None
	width2 = optional will default to edge2 width if None
	e1glayer = glayer for the parts connecting to the edge1. Default to layer of edge1
	e2glayer = glayer for the parts connecting to the edge2. Default to layer of edge2
	cglayer = glayer for the connection part (part that goes through a via) defaults to e1glayer met+1
	viaoffset = offsets the via so that it is flush with the cglayer (may be needed for drc) i.e. -| vs _|
	- True offsets via towards the other via
	- False offsets via away from the other via
	- None means center (no offset)
	***NOTE: viaoffset pushes both vias towards each other slightly
	"""
	# error checking and figure out args
	if round(edge1.orientation) % 90 or round(edge2.orientation) % 90:
		raise ValueError("Ports must be vertical or horizontal")
	if not isclose(edge1.orientation,edge2.orientation):
		raise ValueError("Ports must be parralel and have same orientation")
	width1 = width1 if width1 else edge1.width
	width2 = width2 if width2 else edge1.width
	e1glayer = e1glayer if e1glayer else pdk.layer_to_glayer(edge1.layer)
	e2glayer = e2glayer if e2glayer else pdk.layer_to_glayer(edge2.layer)
	eglayer_plusone = "met" + str(int(e1glayer[-1])+1)
	cglayer = cglayer if cglayer else eglayer_plusone
	if not "met" in e1glayer or not "met" in e2glayer or not "met" in cglayer:
		raise ValueError("given layers must be metals")
	viaoffset = (None, None) if viaoffset is None else viaoffset
	if isinstance(viaoffset,bool):
		viaoffset = (True,True) if viaoffset else (False,False)
	pdk.has_required_glayers([e1glayer,e2glayer,cglayer])
	pdk.activate()
	# create route
	croute = Component()
	viastack1 = via_stack(pdk,e1glayer,cglayer,fullbottom=fullbottom,assume_bottom_via=True)
	viastack2 = via_stack(pdk,e2glayer,cglayer,fullbottom=fullbottom,assume_bottom_via=True)
	if e1glayer == e2glayer:
		__fill_empty_viastack__macro(pdk,e1glayer,size=(width1,width2))
	elif e1glayer == cglayer:
		viastack1 = __fill_empty_viastack__macro(pdk,e1glayer,size=evaluate_bbox(viastack2))
	elif e2glayer == cglayer:
		viastack2 = __fill_empty_viastack__macro(pdk,e2glayer,size=evaluate_bbox(viastack1))
	# find extension
	e1_length = extension + evaluate_bbox(viastack1)[0]
	e2_length = extension + evaluate_bbox(viastack2)[0]
	xdiff = abs(edge1.center[0] - edge2.center[0])
	ydiff = abs(edge1.center[1] - edge2.center[1])
	if not isclose(edge1.center[0],edge2.center[0]):
		if round(edge1.orientation) == 0:# facing east
			if edge1.center[0] > edge2.center[0]:
				e2_length += xdiff
			else:
				e1_length += xdiff
		elif round(edge1.orientation) == 180:# facing west
			if edge1.center[0] < edge2.center[0]:
				e2_length += xdiff
			else:
				e1_length += xdiff
	if not isclose(edge1.center[1],edge2.center[1]):
		if round(edge1.orientation) == 270:# facing south
			if edge1.center[1] < edge2.center[1]:
				e2_length += ydiff
			else:
				e1_length += ydiff
		elif round(edge1.orientation) == 90:#facing north
			if edge1.center[1] > edge2.center[1]:
				e2_length += ydiff
			else:
				e1_length += ydiff
	# move into position
	e1_extension_comp = Component("edge1 extension")
	e2_extension_comp = Component("edge2 extension")
	box_dims = [(e1_length, width1),(e2_length, width2)]
	if round(edge1.orientation) == 90 or round(edge1.orientation) == 270:
		box_dims = [(width1, e1_length),(width2, e2_length)]
	rect_c1 = rectangle(size=box_dims[0], layer=pdk.get_glayer(e1glayer),centered=True).copy()
	rect_c2 = rectangle(size=box_dims[1], layer=pdk.get_glayer(e2glayer),centered=True).copy()
	rect_c1 = rename_ports_by_orientation(rename_ports_by_list(rect_c1,[("e","e_")]))
	rect_c2 = rename_ports_by_orientation(rename_ports_by_list(rect_c2,[("e","e_")]))
	e1_extension = e1_extension_comp << rect_c1
	e2_extension = e2_extension_comp << rect_c2
	e1_extension.move(destination=edge1.center)
	e2_extension.move(destination=edge2.center)
	if round(edge1.orientation) == 0:# facing east
		e1_extension.movex(evaluate_bbox(e1_extension)[0]/2)
		e2_extension.movex(evaluate_bbox(e2_extension)[0]/2)
	elif round(edge1.orientation) == 180:# facing west
		e1_extension.movex(0-evaluate_bbox(e1_extension)[0]/2)
		e2_extension.movex(0-evaluate_bbox(e2_extension)[0]/2)
	elif round(edge1.orientation) == 270:# facing south
		e1_extension.movey(0-evaluate_bbox(e1_extension)[1]/2)
		e2_extension.movey(0-evaluate_bbox(e2_extension)[1]/2)
	else:#facing north
		e1_extension.movey(evaluate_bbox(e1_extension)[1]/2)
		e2_extension.movey(evaluate_bbox(e2_extension)[1]/2)
	# place viastacks
	e1_extension_comp.add_ports(e1_extension.get_ports_list())
	e2_extension_comp.add_ports(e2_extension.get_ports_list())
	me1 = e1_extension_comp << viastack1
	me2 = e2_extension_comp << viastack2
	route_ports = [None,None]
	via_flush = abs((width1 - evaluate_bbox(viastack1)[0])/2) if viaoffset else 0
	via_flush1 = via_flush if viaoffset[0] else 0-via_flush
	via_flush1 = 0 if viaoffset[0] is None else via_flush1
	via_flush2 = via_flush if viaoffset[1] else 0-via_flush
	via_flush2 = 0 if viaoffset[1] is None else via_flush2
	if round(edge1.orientation) == 0:# facing east
		me1.move(destination=e1_extension.ports["e_E"].center)
		me2.move(destination=e2_extension.ports["e_E"].center)
		via_flush *= 1 if me1.ymax > me2.ymax else -1
		me1.movex(0-viastack1.xmax).movey(0-via_flush1)
		me2.movex(0-viastack2.xmax).movey(via_flush2)
		me1, me2 = (me1, me2) if (me1.origin[1] > me2.origin[1]) else (me2, me1)
		route_ports = [me1.ports["top_met_N"],me2.ports["top_met_S"]]
	elif round(edge1.orientation) == 180:# facing west
		me1.move(destination=e1_extension.ports["e_W"].center)
		me2.move(destination=e2_extension.ports["e_W"].center)
		via_flush *= 1 if me1.ymax > me2.ymax else -1
		me1.movex(viastack1.xmax).movey(0-via_flush1)
		me2.movex(viastack2.xmax).movey(via_flush2)
		me1, me2 = (me1, me2) if (me1.origin[1] > me2.origin[1]) else (me2, me1)
		route_ports = [me1.ports["top_met_N"],me2.ports["top_met_S"]]
	elif round(edge1.orientation) == 270:# facing south
		me1.move(destination=e1_extension.ports["e_S"].center)
		me2.move(destination=e2_extension.ports["e_S"].center)
		via_flush *= 1 if me1.xmax > me2.xmax else -1
		me1.movey(viastack1.xmax).movex(0-via_flush1)
		me2.movey(viastack2.xmax).movex(via_flush2)
		me1, me2 = (me1, me2) if (me1.origin[0] > me2.origin[0]) else (me2, me1)
		route_ports = [me1.ports["top_met_E"],me2.ports["top_met_W"]]
	else:#facing north
		me1.move(destination=e1_extension.ports["e_N"].center)
		me2.move(destination=e2_extension.ports["e_N"].center)
		via_flush *= 1 if me1.xmax > me2.xmax else -1
		me1.movey(0-viastack1.xmax).movex(0-via_flush1)
		me2.movey(0-viastack2.xmax).movex(via_flush2)
		me1, me2 = (me1, me2) if (me1.origin[0] > me2.origin[0]) else (me2, me1)
		route_ports = [me1.ports["top_met_E"],me2.ports["top_met_W"]]
	# connect extensions, add ports, return
	croute << e1_extension_comp
	croute << e2_extension_comp
	if cwidth:
		route_ports = [set_port_width(port_,cwidth) for port_ in route_ports]
	route_ports[0].width = route_ports[1].width = max(route_ports[0].width, route_ports[1].width)
	cconnection = croute << route_quad(route_ports[0],route_ports[1],layer=pdk.get_glayer(cglayer))
	for i,port_to_add in enumerate(route_ports):
		orta = get_orientation(port_to_add.orientation)
		#orta = "S" if orta=="N" else ("N" if orta=="S" else orta)
		#orta = "E" if orta=="W" else ("W" if orta=="E" else orta)
		route_ports[i] = set_port_orientation(port_to_add, orta)
	croute.add_ports(route_ports,prefix="con_")
	return rename_ports_by_orientation(rename_ports_by_list(croute.flatten(), [("con_","con_")]))

if __name__ == "__main__":
	from .pdk.util.standard_main import pdk
	
	routebetweentop = copy(rectangle(layer=pdk.get_glayer("met1"))).ref()
	routebetweentop.movey(10)
	routebetweenbottom = rectangle(layer=pdk.get_glayer("met1"))
	mycomp = c_route(pdk,routebetweentop.ports["e3"],routebetweenbottom.ports["e3"])
	mycomp.unlock()
	mycomp.add(routebetweentop)
	mycomp << routebetweenbottom
	mycomp.flatten().show()
