# 1- create single transistor component
# 2- create a 4 array of them with top transistors mirrored along xaxis such that gate routes are facing out
#		separation in the middle should be max of 

from gdsfactory.cell import cell
from gdsfactory.component import Component, copy
from gdsfactory.components.rectangle import rectangle
from .fet import nmos, pmos
from .pdk.mappedpdk import MappedPDK
from typing import Optional
from gdsfactory.routing.route_quad import route_quad
from gdsfactory.routing.route_sharp import route_sharp
from .c_route import c_route
from .pdk.util.comp_utils import movex, movey, evaluate_bbox, align_comp_to_port
from .pdk.util.port_utils import rename_ports_by_orientation, rename_ports_by_list, add_ports_perimeter, print_ports, get_orientation, set_port_orientation
from .via_gen import via_stack
from .pdk.util.snap_to_grid import component_snap_to_grid


@cell
def diff_pair(
	pdk: MappedPDK,
	width: Optional[float] = 3,
	fingers: Optional[int] = 4,
	length: Optional[float] = None,
	n_or_p_fet: Optional[bool] = True,
	plus_minus_seperation: Optional[float] = 0,
	rmult: int = 1
) -> Component:
	"""create a diffpair with 2 transistors placed in two rows with common centroid place. Sources are shorted
	width = width of the transistors
	fingers = number of fingers in the transistors (must be 2 or more)
	length = length of the transistors, None or 0 means use min length
	short_source = if true connects source of both transistors
	n_or_p_fet = if true the diffpair is made of nfets else it is made of pfets
	"""
	# TODO: error checking
	pdk.activate()
	diffpair = Component()
	# create transistors
	well = None
	if n_or_p_fet:
		fet = nmos(pdk, width=width, fingers=fingers,length=length,multipliers=1,with_tie=False,with_dummy=False,with_dnwell=False,with_substrate_tap=False,rmult=rmult)
		#print_ports(fet)
		min_spacing_x = pdk.get_grule("n+s/d")["min_separation"] - 2*(fet.xmax - fet.ports["multiplier_0_plusdoped_E"].center[0])
		well = "pwell"
	else:
		fet = pmos(pdk, width=width, fingers=fingers,length=length,multipliers=1,with_tie=False,with_dummy=False,dnwell=False,with_substrate_tap=False,rmult=rmult)
		min_spacing_x = pdk.get_grule("p+s/d")["min_separation"] - 2*(fet.xmax - fet.ports["multiplier_0_plusdoped_E"].center[0])
		well = "nwell"
	# place transistors
	viam2m3 = via_stack(pdk,"met2","met3",centered=True)
	metal_min_dim = max(pdk.get_grule("met2")["min_width"],pdk.get_grule("met3")["min_width"])
	metal_space = max(pdk.get_grule("met2")["min_separation"],pdk.get_grule("met3")["min_separation"],metal_min_dim)
	gate_route_os = evaluate_bbox(viam2m3)[0] - fet.ports["multiplier_0_gate_W"].width + metal_space
	min_spacing_y = metal_space + 2*gate_route_os
	min_spacing_y = min_spacing_y - 2*abs(fet.ports["well_S"].center[1] - fet.ports["multiplier_0_gate_S"].center[1])
	# TODO: fix spacing where you see +-0.5
	a_topl = (diffpair << fet).movey(fet.ymax+min_spacing_y/2+0.5).movex(0-fet.xmax-min_spacing_x/2)
	b_topr = (diffpair << fet).movey(fet.ymax+min_spacing_y/2+0.5).movex(fet.xmax+min_spacing_x/2)
	a_botr = (diffpair << fet)
	a_botr.mirror_y().movey(0-0.5-fet.ymax-min_spacing_y/2).movex(fet.xmax+min_spacing_x/2)
	b_botl = (diffpair << fet)
	b_botl.mirror_y().movey(0-0.5-fet.ymax-min_spacing_y/2).movex(0-fet.xmax-min_spacing_x/2)
	# route sources (short sources)
	diffpair << route_quad(a_topl.ports["multiplier_0_source_E"], b_topr.ports["multiplier_0_source_W"], layer=pdk.get_glayer("met2"))
	diffpair << route_quad(b_botl.ports["multiplier_0_source_E"], a_botr.ports["multiplier_0_source_W"], layer=pdk.get_glayer("met2"))
	sextension = b_topr.ports["well_E"].center[0] - b_topr.ports["multiplier_0_source_E"].center[0]
	source_routeE = diffpair << c_route(pdk, b_topr.ports["multiplier_0_source_E"], a_botr.ports["multiplier_0_source_E"],extension=sextension)
	source_routeW = diffpair << c_route(pdk, a_topl.ports["multiplier_0_source_W"], b_botl.ports["multiplier_0_source_W"],extension=sextension)
	# route drains
	# place via at the drain
	drain_br_via = diffpair << viam2m3
	drain_bl_via = diffpair << viam2m3
	drain_br_via.move(a_botr.ports["multiplier_0_drain_N"].center).movey(viam2m3.ymin)
	drain_bl_via.move(b_botl.ports["multiplier_0_drain_N"].center).movey(viam2m3.ymin)
	drain_br_viatm = diffpair << viam2m3
	drain_bl_viatm = diffpair << viam2m3
	drain_br_viatm.move(a_botr.ports["multiplier_0_drain_N"].center).movey(viam2m3.ymin)
	drain_bl_viatm.move(b_botl.ports["multiplier_0_drain_N"].center).movey(-1.5 * evaluate_bbox(viam2m3)[1] - metal_space)
	# create route to drain via
	width_drain_route = b_topr.ports["multiplier_0_drain_E"].width
	dextension = source_routeE.xmax - b_topr.ports["multiplier_0_drain_E"].center[0] + metal_space
	bottom_extension = viam2m3.ymax + width_drain_route/2 + 2*metal_space
	drain_br_viatm.movey(0-bottom_extension - metal_space - width_drain_route/2 - viam2m3.ymax)
	diffpair << route_quad(drain_br_viatm.ports["top_met_N"], drain_br_via.ports["top_met_S"], layer=pdk.get_glayer("met3"))
	diffpair << route_quad(drain_bl_viatm.ports["top_met_N"], drain_bl_via.ports["top_met_S"], layer=pdk.get_glayer("met3"))
	floating_port_drain_bottom_L = set_port_orientation(movey(drain_bl_via.ports["bottom_met_W"],0-bottom_extension), get_orientation("E"))
	floating_port_drain_bottom_R = set_port_orientation(movey(drain_br_via.ports["bottom_met_E"],0-bottom_extension - metal_space - width_drain_route), get_orientation("W"))
	drain_routeTR_BL = diffpair << c_route(pdk, floating_port_drain_bottom_L, b_topr.ports["multiplier_0_drain_E"],extension=dextension, width1=width_drain_route,width2=width_drain_route)
	drain_routeTL_BR = diffpair << c_route(pdk, floating_port_drain_bottom_R, a_topl.ports["multiplier_0_drain_W"],extension=dextension, width1=width_drain_route,width2=width_drain_route)
	# cross gate route top with c_route. bar_minus ABOVE bar_plus
	get_left_extension = lambda bar, a_topl=a_topl, diffpair=diffpair, pdk=pdk : (abs(diffpair.xmin-min(a_topl.ports["multiplier_0_gate_W"].center[0],bar.ports["e1"].center[0])) + pdk.get_grule("met2")["min_separation"])
	get_right_extension = lambda bar, b_topr=b_topr, diffpair=diffpair, pdk=pdk : (abs(diffpair.xmax-max(b_topr.ports["multiplier_0_gate_E"].center[0],bar.ports["e3"].center[0])) + pdk.get_grule("met2")["min_separation"])
	# lay bar plus and PLUSgate_routeW
	bar_comp = rectangle(centered=True,size=(abs(b_topr.xmax-a_topl.xmin), b_topr.ports["multiplier_0_gate_E"].width),layer=pdk.get_glayer("met2"))
	bar_plus = (diffpair << bar_comp).movey(diffpair.ymax + bar_comp.ymax + pdk.get_grule("met2")["min_separation"])
	PLUSgate_routeW = diffpair << c_route(pdk, a_topl.ports["multiplier_0_gate_W"], bar_plus.ports["e1"], extension=get_left_extension(bar_plus))
	#lay bar minus and MINUSgate_routeE
	plus_minus_seperation = max(pdk.get_grule("met2")["min_separation"], plus_minus_seperation)
	bar_minus = (diffpair << bar_comp).movey(diffpair.ymax +bar_comp.ymax + plus_minus_seperation)
	MINUSgate_routeE = diffpair << c_route(pdk, b_topr.ports["multiplier_0_gate_E"], bar_minus.ports["e3"], extension=get_right_extension(bar_minus))
	# lay MINUSgate_routeW and PLUSgate_routeE
	MINUSgate_routeW = diffpair << c_route(pdk, set_port_orientation(b_botl.ports["multiplier_0_gate_E"],"W"), bar_minus.ports["e1"], extension=get_left_extension(bar_minus))
	PLUSgate_routeE = diffpair << c_route(pdk, set_port_orientation(a_botr.ports["multiplier_0_gate_W"],"E"), bar_plus.ports["e3"], extension=get_right_extension(bar_plus))
	# correct pwell place, add ports, flatten, and return
	diffpair.add_ports(a_topl.get_ports_list(),prefix="tl_")
	diffpair.add_ports(b_topr.get_ports_list(),prefix="tr_")
	diffpair.add_ports(b_botl.get_ports_list(),prefix="bl_")
	diffpair.add_ports(a_botr.get_ports_list(),prefix="br_")
	diffpair.add_ports(source_routeE.get_ports_list(),prefix="source_routeE_")
	diffpair.add_ports(source_routeW.get_ports_list(),prefix="source_routeW_")
	diffpair.add_ports(drain_routeTR_BL.get_ports_list(),prefix="drain_routeTR_BL_")
	diffpair.add_ports(drain_routeTL_BR.get_ports_list(),prefix="drain_routeTL_BR_")
	diffpair.add_ports(MINUSgate_routeW.get_ports_list(),prefix="MINUSgateroute_W_")
	diffpair.add_ports(MINUSgate_routeE.get_ports_list(),prefix="MINUSgateroute_E_")
	diffpair.add_ports(PLUSgate_routeW.get_ports_list(),prefix="PLUSgateroute_W_")
	diffpair.add_ports(PLUSgate_routeE.get_ports_list(),prefix="PLUSgateroute_E_")
	diffpair.add_padding(layers=(pdk.get_glayer(well),), default=0)
	return component_snap_to_grid(rename_ports_by_orientation(diffpair))


if __name__ == "__main__":
	from .pdk.util.standard_main import pdk
	mycomp = diff_pair(pdk,length=1,width=6,fingers=4,rmult=2)
	mycomp.show()
	print_ports(mycomp)

