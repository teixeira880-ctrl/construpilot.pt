#!/bin/bash
# Junta a voz (ElevenLabs) ao vídeo já montado: o vídeo não é recodificado.
# Uso: juntar_voz.sh <video-sem-voz.mp4> <pasta dos mp3> <saida.mp4>
set -e
V="$1"; A="$2"; O="$3"
ffmpeg -y -v error -i "$V" -i "$A/01_intro.mp3" -i "$A/02_desenhar.mp3" -i "$A/03_vaos.mp3" -i "$A/04_mobiliario.mp3" -i "$A/05_materiais.mp3" -i "$A/06_3d.mp3" -i "$A/07_visita.mp3" -i "$A/08_alcados.mp3" -i "$A/09_medicoes.mp3" -i "$A/10_exportar.mp3" -i "$A/11_fim.mp3" -filter_complex "[1:a]adelay=2650:all=1[a0];[2:a]adelay=19575:all=1[a1];[3:a]adelay=41280:all=1[a2];[4:a]adelay=55409:all=1[a3];[5:a]adelay=72151:all=1[a4];[6:a]adelay=85680:all=1[a5];[7:a]adelay=101769:all=1[a6];[8:a]adelay=109551:all=1[a7];[9:a]adelay=117646:all=1[a8];[10:a]adelay=129660:all=1[a9];[11:a]adelay=145096:all=1[a10];[a0][a1][a2][a3][a4][a5][a6][a7][a8][a9][a10]amix=inputs=11:normalize=0:dropout_transition=0,apad[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k -ar 44100 -ac 2 -shortest -movflags +faststart "$O.tmp.mp4"
mv "$O.tmp.mp4" "$O"
ffprobe -v error -show_entries format=duration,size -of csv=p=0 "$O"
