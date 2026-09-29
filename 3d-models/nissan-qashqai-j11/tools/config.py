"""Meshes of the default configuration (nconnecta_16dci_m.pc), inferred from
the part names (the JBeam that maps parts to meshes is not in the package).
Pre-facelift (_a / no suffix) exterior; LHD driver's controls.  RHD_SWAP lists
the mod's own right-hand-drive replacements."""

L_R = ("L", "R")
FRONT_REAR = ("FL", "FR", "RL", "RR")

EXTERIOR = [
    "qashqai16_body", "qashqai16_body_notwide", "qashqai16_roof", "qashqai16_roof_rack", "qashqai16_antenna",
    "qashqai16_hood_a", "qashqai16_bumper_a_F", "qashqai16_bumper_F_notwide", "qashqai16_grille_a", "qashqai16_logo_F",
    "qashqai16_bumper_a_R", "qashqai16_bumper_R_notwide", "qashqai16_bumper_a_R_diffuser", "circle",
    "qashqai16_fender_FL", "qashqai16_fender_FR", "qashqai16_fender_FL_notwide", "qashqai16_fender_FR_notwide",
    "qashqai16_windshield", "qashqai16_windshield_int", "qashqai16_tailgateglass", "qashqai16_tailgateglass_int",
    "qashqai16_sideglass_RL", "qashqai16_sideglass_RL_int", "qashqai16_sideglass_RR", "qashqai16_sideglass_RR_int",
    "qashqai16_tailgate_a", "qashqai16_tailgate_spoiler", "qashqai16_tailgate_chmsl", "qashqai16_tailgate_chmsl_glass",
    "qashqai16_wiper_RR", "qashqai16_tailgate_struts", "qashqai16_tailgate_a_light_frame",
    "qashqai16_logo_R", "qashqai16_lettering_R", "qashqai16_fueldoor", "qashqai16_wipersbase_F", "qashqai16_wipers_F",
    "qashqai16_exhaustpipe_single", "1qashqai16_licenseplate_F", "1qashqai16_licenseplate_R",
] + ["qashqai16_door_%s" % s for s in FRONT_REAR] \
  + ["qashqai16_doorglass_%s_openable" % s for s in FRONT_REAR] + ["qashqai16_doorglass_%s_int_openable" % s for s in FRONT_REAR] \
  + [p % s for s in L_R for p in ("qashqai16_headlight_%s_base", "qashqai16_headlightframe_%s", "qashqai16_headlightframe_plastic_%s",
                                  "qashqai16_headlightglass_%s", "qashqai16_taillight_%s", "qashqai16_taillightframe_%s",
                                  "qashqai16_taillightglass_%s", "qashqai16_taillightglass_%s_red", "qashqai16_tailgate_a_light_%s",
                                  "qashqai16_tailgate_a_lightglass_%s", "qashqai16_tailgate_a_lightglass_%s_red",
                                  "qashqai16_mirror_%s", "qashqai16_mirrorglass_%s", "qashqai16_mirrorlight_%s",
                                  "qashqai16_mirrorlightglass_%s", "qashqai16_tailgate_lamp_%s", "qashqai16_tailgate_lamp_%s_frame",
                                  "qashqai16_tailgate_lamp_%s_glass")] \
  + [p % s for s in ("FL", "FR") for p in ("qashqai16_foglight_%s", "qashqai16_foglightframe_%s", "qashqai16_foglightglass_%s")]

INTERIOR = [
    "qashqai16_int", "qashqai16_int_ceiling", "qashqai16_panels", "qashqai16_dash", "qashqai16_dash_gps", "qashqai16_dash_ac",
    "qashqai16_dash_ac_display", "qashqai16_navi", "qashqai16_navi_data", "qashqai16_gauges", "qashqai16_gauges_display",
    "qashqai16_gauges_screen", "qashqai16_decals_gauges", "qashqai16_needle_temp", "qashqai16_needle_tacho",
    "qashqai16_needle_speedo", "qashqai16_needle_fuel", "qashqai16_steer", "qashqai16_signalstalk", "qashqai16_wiperstalk",
    "qashqai16_startstop_button", "qashqai16_pedal_gas", "qashqai16_pedal_clutch", "qashqai16_pedal_brake",
    "qashqai16_parkingbrake", "qashqai16_console", "qashqai16_console_shifterpart", "qashqai16_shifter_knob_M",
    "qashqai16_shifter_boot_M", "qashqai16_shifter_base_M", "qashqai16_armrest", "qashqai16_gloveboxdoor", "qashqai16_int_mirror",
    "qashqai16_sunvisor_l", "qashqai16_sunvisor_r", "qashqai16_sunvisor_support_l", "qashqai16_sunvisor_support_r",
    "qashqai16_domelight", "qashqai16_domelight_light", "qashqai16_domelight_lightglass", "qashqai16_domelights_rear",
    "qashqai16_domelights_glass_rear", "qashqai16_domelights_frame_rear", "qashqai16_doorpanel_FL", "qashqai16_doorpanel_FR",
    "qashqai16_doorpanel_RL", "qashqai16_doorpanel_RR", "qashqai16_doorpanel_FL_mir_adj", "qashqai16_seats_R",
    "qashqai16_seats_R_trim", "qashqai16_doorsill_plates_b", "qashqai16_floormats_b", "qashqai16_shelf",
    "qashqai16_spare_compartment",
] + ["qashqai16_speakers_%s" % s for s in FRONT_REAR] \
  + [p % s for s in ("FL", "FR") for p in ("qashqai16_seat_%s", "qashqai16_seat_%s_back", "qashqai16_seat_%s_support",
                                           "qashqai16_seat_%s_trim", "qashqai16_seat_%s_trim_back")]

MECHANICAL = [
    "qashqai16_underbody", "qashqai16_underbody_cover", "qashqai16_tubs_F", "qashqai16_engbay", "qashqai16_radsupport",
    "qashqai16_raerbeam", "qashqai16_tray_F", "qashqai16_engine_DCI", "qashqai16_engine_i4", "qashqai16_turbo_i4",
    "qashqai16_intercooler", "qashqai16_intake_i4", "qashqai16_airbox", "qashqai16_radiator", "qashqai16_radfan1",
    "qashqai16_radfan2", "qashqai16_transmission", "qashqai16_exhaust", "qashqai16_fueltank",
    "qashqai16_subframe_F", "qashqai16_lowerarm_F", "qashqai16_tierod_F", "qashqai16_strut_front", "qashqai16_swaybar_F",
    "qashqai16_halfshaft_F", "qashqai16_hub_FL", "qashqai16_hub_FR",
    "qashqai16_subframe_R", "qashqai16_lowerarm_R", "qashqai16_upperarm_R", "qashqai16_trailingarm_R", "qashqai16_wishbone_R",
    "qashqai16_spring_R", "qashqai16_shock_R", "qashqai16_hub_R",
]

WHEEL = "qashqai16_wheel_nconnecta"

# the mod's right-hand-drive variants (used by its _rhd configurations)
RHD_SWAP = {
    "qashqai16_dash": "qashqai16_dash_rhd", "qashqai16_gauges": "qashqai16_gauges_rhd",
    "qashqai16_gauges_display": "qashqai16_gauges_display_rhd", "qashqai16_gauges_screen": "qashqai16_gauges_screen_rhd",
    "qashqai16_decals_gauges": "qashqai16_decals_gauges_rhd", "qashqai16_needle_temp": "qashqai16_needle_temp_rhd",
    "qashqai16_needle_tacho": "qashqai16_needle_tacho_rhd", "qashqai16_needle_speedo": "qashqai16_needle_speedo_rhd",
    "qashqai16_needle_fuel": "qashqai16_needle_fuel_rhd", "qashqai16_steer": "qashqai16_steer_rhd",
    "qashqai16_signalstalk": "qashqai16_signalstalk_rhd", "qashqai16_wiperstalk": "qashqai16_wiperstalk_rhd",
    "qashqai16_startstop_button": "qashqai16_startstop_button_rhd", "qashqai16_pedal_gas": "qashqai16_pedal_gas_rhd",
    "qashqai16_pedal_clutch": "qashqai16_pedal_clutch_rhd", "qashqai16_pedal_brake": "qashqai16_pedal_brake_rhd",
    "qashqai16_parkingbrake": "qashqai16_parkingbrake_rhd", "qashqai16_gloveboxdoor": "qashqai16_gloveboxdoor_rhd",
    "qashqai16_int_mirror": "qashqai16_int_mirror_rhd", "qashqai16_doorpanel_FL": "qashqai16_doorpanel_FL_rhd",
    "qashqai16_doorpanel_FR": "qashqai16_doorpanel_FR_rhd", "qashqai16_doorpanel_FL_mir_adj": "qashqai16_doorpanel_FR_mir_adj",
    "qashqai16_mirrorglass_L": "qashqai16_mirrorglass_L_rhd", "qashqai16_mirrorglass_R": "qashqai16_mirrorglass_R_rhd",
    "qashqai16_wipers_F": "qashqai16_wipers_F_rhd",
}


def selection(rhd=True):
    names = EXTERIOR + INTERIOR + MECHANICAL
    if rhd:
        names = [RHD_SWAP.get(n, n) for n in names]
    return names
