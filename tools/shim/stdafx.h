// Minimal stand-in for the game's src\stdafx.h, so lib\pklib can be compiled into the
// small offline mpq tools without dragging in the whole engine.
#pragma once
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { SHA1_BLOCK_SIZE = 64 };
struct AppendRec { unsigned int a, b, c, d; };

#include "pklib.h"
