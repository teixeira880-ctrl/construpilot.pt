#!/bin/bash
# Junta a voz (ElevenLabs) ao vídeo já montado: o vídeo não é recodificado.
# Uso: juntar_voz.sh <video-sem-voz.mp4> <pasta dos mp3> <saida.mp4> [ffmpeg]
set -e
V="$1"; A="$2"; O="$3"; FF="${4:-ffmpeg}"
"$FF" -y -v error -i "$V" -i "$A/01_intro.mp3" -i "$A/02_assistente.mp3" -i "$A/03_estimar.mp3" -i "$A/04_plantas.mp3" -i "$A/05_orcamentos.mp3" -i "$A/06_precos.mp3" -i "$A/07_faturacao.mp3" -i "$A/08_obra.mp3" -i "$A/09_engenharia.mp3" -i "$A/10_licenciamento.mp3" -i "$A/11_imagens.mp3" -i "$A/12_empresa.mp3" -i "$A/13_fim.mp3" -filter_complex "[1:a]adelay=2650:all=1[a0];[2:a]adelay=23885:all=1[a1];[3:a]adelay=49090:all=1[a2];[4:a]adelay=71631:all=1[a3];[5:a]adelay=101330:all=1[a4];[6:a]adelay=131577:all=1[a5];[7:a]adelay=155476:all=1[a6];[8:a]adelay=171200:all=1[a7];[9:a]adelay=194263:all=1[a8];[10:a]adelay=226835:all=1[a9];[11:a]adelay=257474:all=1[a10];[12:a]adelay=280956:all=1[a11];[13:a]adelay=303862:all=1[a12];[a0][a1][a2][a3][a4][a5][a6][a7][a8][a9][a10][a11][a12]amix=inputs=13:normalize=0:dropout_transition=0,apad[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k -ar 44100 -ac 2 -shortest -movflags +faststart "$O.tmp.mp4"
mv "$O.tmp.mp4" "$O"
