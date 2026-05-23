CXX := g++
CC := gcc
CXXFLAGS := -std=c++17 -Wall -Wextra -pedantic -Iinclude -Ithird_party
CFLAGS := -O2 -DSQLITE_THREADSAFE=1 -DSQLITE_DEFAULT_MEMSTATUS=0
OPENSSL_CXXFLAGS ?=
OPENSSL_LDFLAGS ?=
LDFLAGS := -lws2_32 -lwinhttp
SHELL := cmd.exe
.SHELLFLAGS := /C

SRC := $(filter-out src/main.cpp,$(wildcard src/*.cpp))
APP_SRC := src/main.cpp $(SRC)
TEST_SRC := tests/test_main.cpp $(SRC)
SQLITE_OBJ := bin\sqlite3.o

APP := bin\tourpass.exe
TEST_APP := bin\tourpass_tests.exe

.PHONY: build run test validate-data test-import-real-pois test-amap-pipeline fetch-amap build-amap-edges algorithm-quality container-smoke load-test clean

build: $(APP)

$(SQLITE_OBJ): third_party\sqlite3.c
	@if not exist bin mkdir bin
	$(CC) $(CFLAGS) -c third_party\sqlite3.c -o $(SQLITE_OBJ)

$(APP): $(APP_SRC) $(SQLITE_OBJ)
	@if not exist bin mkdir bin
	$(CXX) $(CXXFLAGS) $(OPENSSL_CXXFLAGS) $(APP_SRC) $(SQLITE_OBJ) -o $(APP) $(LDFLAGS) $(OPENSSL_LDFLAGS)

$(TEST_APP): $(TEST_SRC) $(SQLITE_OBJ)
	@if not exist bin mkdir bin
	$(CXX) $(CXXFLAGS) $(OPENSSL_CXXFLAGS) $(TEST_SRC) $(SQLITE_OBJ) -o $(TEST_APP) $(LDFLAGS) $(OPENSSL_LDFLAGS)

run: build
	$(APP)

test: $(TEST_APP)
	$(TEST_APP)

validate-data:
	node scripts\validate_data.js

test-import-real-pois:
	node tests\test_import_real_pois.js

test-amap-pipeline:
	node tests\test_amap_pipeline.js

fetch-amap:
	node scripts\fetch_amap_pois.js --config config\amap.changsha.json --out-dir output\amap-changsha

build-amap-edges:
	node scripts\build_commute_edges.js --pois output\amap-changsha\pois.json --out-dir output\amap-changsha --neighbors 6

algorithm-quality:
	node scripts\algorithm_quality_check.js

container-smoke:
	node scripts\container_smoke.js

load-test:
	node scripts\load_test.js

clean:
	@if exist bin rmdir /S /Q bin
	@if exist build rmdir /S /Q build
