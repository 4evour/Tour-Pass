CXX := g++
CXXFLAGS := -std=c++17 -Wall -Wextra -pedantic -Iinclude -Ithird_party
LDFLAGS := -lws2_32
SHELL := cmd.exe
.SHELLFLAGS := /C

SRC := $(filter-out src/main.cpp,$(wildcard src/*.cpp))
APP_SRC := src/main.cpp $(SRC)
TEST_SRC := tests/test_main.cpp $(SRC)

APP := bin\tourpass.exe
TEST_APP := bin\tourpass_tests.exe

.PHONY: build run test clean

build: $(APP)

$(APP): $(APP_SRC)
	@if not exist bin mkdir bin
	$(CXX) $(CXXFLAGS) $(APP_SRC) -o $(APP) $(LDFLAGS)

$(TEST_APP): $(TEST_SRC)
	@if not exist bin mkdir bin
	$(CXX) $(CXXFLAGS) $(TEST_SRC) -o $(TEST_APP) $(LDFLAGS)

run: build
	$(APP)

test: $(TEST_APP)
	$(TEST_APP)

clean:
	@if exist bin rmdir /S /Q bin
	@if exist build rmdir /S /Q build
