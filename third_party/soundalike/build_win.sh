version="0.1.4"
GOOS=windows GOARCH=amd64 CGO_ENABLED=1 CC=x86_64-w64-mingw32-gcc CXX=x86_64-w64-mingw32-g++ go build -o soundalike.exe -ldflags "-s -w -X main.buildVersion=${version}"