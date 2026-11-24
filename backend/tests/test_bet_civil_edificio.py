"""Um edifício com muros de suporte / arruamento no processo não é recusado como «engenharia civil» (Coimbra 24/11)."""
from engines.bet_frame import reader as R


def test_edificio_com_arruamento_nao_e_civil():
    txt = ("Planta da Cave Planta do Res do Chao Planta do 1 Andar quarto sala cozinha I.S. laje pilares sapatas piso "
           "arruamento arruamento muro de suporte")
    assert R.detect_text([], "", txt) != "civil"


def test_obra_civil_sem_edificio_continua_civil():
    assert R.detect_text([], "", "ponte sobre o rio viaduto passagem inferior arruamento pavimentação") == "civil"
