
import os, subprocess
from PIL import Image, ImageDraw
D = "/home/hermes/workspace/convert/testdata"
os.makedirs(D, exist_ok=True)

# картинка с альфой
img = Image.new("RGBA", (800, 600), (0,0,0,0))
d = ImageDraw.Draw(img)
for y in range(600):
    d.line([(0,y),(800,y)], fill=(20+y//4, 200-y//5, 120, 255))
d.ellipse((150,100,650,500), fill=(216,255,62,255))
d.text((40,40), "FORMA test", fill=(0,0,0,255))
img.save(f"{D}/sample.png")
img.convert("RGB").save(f"{D}/sample.jpg", quality=92)
img.save(f"{D}/sample.webp", quality=90)
img.convert("RGB").save(f"{D}/sample.bmp")
img.convert("RGB").save(f"{D}/sample.tiff")
img.save(f"{D}/sample.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
img.convert("RGB").save(f"{D}/sample.avif", quality=80) if False else None

# gif
frames = [img.convert("RGB").rotate(a) for a in (0, 8, 16, 8)]
frames[0].save(f"{D}/sample.gif", save_all=True, append_images=frames[1:], duration=120, loop=0)

# svg
open(f"{D}/sample.svg","w").write("""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
<rect width="400" height="400" fill="#0b0c0e"/><circle cx="200" cy="200" r="140" fill="#d8ff3e"/>
<text x="200" y="215" font-family="sans-serif" font-size="42" text-anchor="middle" fill="#0a0b00">SVG</text></svg>""")

# аудио
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","sine=frequency=440:duration=3",
                "-c:a","pcm_s16le",f"{D}/sample.wav"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.wav","-c:a","libmp3lame","-b:a","192k",f"{D}/sample.mp3"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.wav","-c:a","libvorbis",f"{D}/sample.ogg"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.wav","-c:a","flac",f"{D}/sample.flac"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.wav","-c:a","aac",f"{D}/sample.m4a"], check=True)

# видео
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","testsrc2=size=640x480:rate=25:duration=3",
                "-f","lavfi","-i","sine=frequency=330:duration=3","-c:v","libx264","-pix_fmt","yuv420p",
                "-c:a","aac","-shortest",f"{D}/sample.mp4"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.mp4","-c:v","libvpx-vp9","-crf","36","-b:v","0",
                "-c:a","libopus",f"{D}/sample.webm"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.mp4","-c","copy",f"{D}/sample.mov"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.mp4","-c","copy",f"{D}/sample.mkv"], check=True)
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",f"{D}/sample.mp4","-vf","fps=10,scale=320:-1","-loop","0",f"{D}/sample_video.gif"], check=True)

# документы
open(f"{D}/sample.txt","w").write("FORMA test document\n\nLine two with numbers 12345.\n" * 20)
open(f"{D}/sample.md","w").write("# Заголовок\n\nТекст **жирный** и *курсив*.\n\n- пункт один\n- пункт два\n\n```\ncode block\n```\n")
open(f"{D}/sample.html","w").write("<html><body><h1>FORMA</h1><p>Тестовый HTML-документ.</p></body></html>")
open(f"{D}/sample.csv","w").write("name,value,note\nalpha,1,first\nbeta,2,second\ngamma,3,third\n")

print("\n".join(sorted(os.listdir(D))))
