cd ../
if (Test-Path dist/) { Remove-Item dist/ -Recurse -Force }
if (Test-Path build/) { Remove-Item build/ -Recurse -Force }
mkdir dist
mkdir dist/dist
mkdir dist/dist/conf
pyinstaller .\main.py -F
mv dist/main.exe dist/dist/gits.exe
cp dist/dist/gits.exe dist/dist/gis.exe
cp conf/config.json dist/dist/conf/config.json
cp main.py dist/main.py
