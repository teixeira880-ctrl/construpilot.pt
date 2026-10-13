"""Explicit fictitious drawing fixture, never attached to a real PC."""
from engines.structuro_calc import example
from engines.structuro_drawings import DrawingStudy


def drawing_example():
    model=example();model.title="EXEMPLE FICTIF - dossier coffrage et aciers"
    source="Exemple pédagogique. Dimensions et aciers choisis, non dimensionnés."
    # Display elevations are explicit, not inferred from storey names.
    # Shift only foundations to centre their column/wall footprint in the drawing.
    for e in model.elements:
        if e.id in ("S1","S2"):e.x_m-=.35;e.y_m-=.35
        if e.id=="S3":e.y_m-=.2
    def point(x,y,z):return dict(x=x,y=y,z=z)
    model.drawings=DrawingStudy.model_validate(dict(basis="demonstration",
        placements=[dict(element_id=e.id,base_z_m={"Fondations":-.3,"RDC":0.,"R+1":2.8}[e.level]-(.25 if e.id=="B1" else 0),source=source) for e in model.elements],
        openings=[dict(id="T1",element_id="D1",x_m=2.,y_m=1.8,z_m=0.,length_m=.8,width_m=.7,height_m=.2,source=source)],
        cuts=[dict(id="AA",axis="x",at_m=.15),dict(id="BB",axis="y",at_m=2.4)],
        bars=[dict(mark="A01",element_id="D1",diameter_mm=10.,count=8,points=[point(.06,.1,.055),point(3.94,.1,.055)],repeat=point(0.,.2,0.),bend_radius_mm=0.,cover_mm=25.,source=source,role="Nappe locale, zone hors trémie"),
              dict(mark="A02",element_id="B1",diameter_mm=16.,count=2,points=[point(.1,.065,.36),point(.1,.065,.065),point(3.9,.065,.065),point(3.9,.065,.36)],repeat=point(0.,.12,0.),bend_radius_mm=40.,cover_mm=25.,source=source,role="Barres en U, ancrages non vérifiés"),
              dict(mark="A03",element_id="S1",diameter_mm=12.,count=5,points=[point(.07,.1,.08),point(.93,.1,.08)],repeat=point(0.,.2,0.),bend_radius_mm=0.,cover_mm=50.,source=source,role="Semelle : nappe illustrative dans une direction")],
        notes=["Exemple indépendant de tout chantier. Le ferraillage montré est partiel : il illustre le dessin, pas une cage complète.","La réservation T1 est une donnée de dessin. Sa présence nécessite une adaptation du modèle porteur avant une étude réelle."]))
    return model


def automation_example():
    """No input bars, cuts or element elevations: generated in one run."""
    from engines.structuro_automation import AutomationSettings
    from engines.structuro_calc import Combination,Source
    m=drawing_example();m.title='EXEMPLE FICTIF - chaîne automatique ConstruPilot'
    m.drawings.bars=[];m.drawings.cuts=[];m.drawings.placements=[];m.drawings.openings=[]
    m.drawings.notes=['Exemple fictif sans trémie : règle de dalle unidirectionnelle explicitement choisie. Valeurs de sol fictives, sans rapport G2 réel.']
    src=Source(note='Exemple fictif : combinaisons et données choisies pour tester le logiciel.')
    m.combinations=[Combination(id='ELS',label='Exemple ELS',factors={'G':1.,'Q':1.},source=src),Combination(id='ELU',label='Exemple ELU',factors={'G':1.35,'Q':1.5},source=src)]
    m.automation_settings=AutomationSettings.model_validate(dict(confirmed=True,
        materials=dict(fck_mpa=25.,fyk_mpa=500.,fctm_mpa=2.6,gamma_c=1.5,gamma_s=1.15,alpha_cc=1.,source='Profil de démonstration C25/30 et B500, sans validation de chantier.'),
        cover_mm=30.,aggregate_mm=20.,fctk005_mpa=1.8,bond_eta1=.7,uls_case_ids=['ELU'],rc_element_ids=['D1','B1'],
        slab_span_axes={'D1':'y'},level_base_z_m={'RDC':0.,'Fondations':-.3},level_top_z_m={'R+1':3.},
        source='Profil de démonstration confirmé pour essai logiciel seulement.',
        foundations=[dict(element_id=e.id,mode='strip' if e.id=='S3' else 'square_pad',sls_case_ids=['ELS'],uls_case_ids=['ELU'],q_sls_kpa=150.,q_uls_kpa=220.,min_width_m=.5,max_width_m=2.,width_step_m=.05,same_site_confirmed=True,centred_vertical_confirmed=True,soil_source='SOL FICTIF DE DÉMONSTRATION, ne provient pas de La Courneuve ni de Saint-Denis.') for e in m.elements if e.kind=='footing']))
    return m
