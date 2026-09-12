// Small offline helper used while authoring interface assets: pulls named files out of a
// v0 MPQ archive (DIABDAT.MPQ, TH4data.mor, ...) so their graphics can be inspected and
// re-worked. Reads the archive directly (hash/block tables + PKWARE-imploded sectors,
// which is all Diablo-era archives use) and decompresses with the pklib explode() that
// already ships in lib\pklib.
//
// build: see tools\build_mpq_tools.bat
// usage: mpq_extract <archive.mpq> <outdir> <file-in-mpq> [more files...]
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

// pklib.h's tail references these engine types (see src\enums.h / src\structs.h); the tool
// never calls that helper, it just has to compile.
enum { SHA1_BLOCK_SIZE = 64 };
struct AppendRec { unsigned int a, b, c, d; };
#include "pklib.h"

//-----------------------------------------------------------------------------
// Storm's crypt table / string hashing / block decryption

static unsigned int CryptTable[0x500];

static void PrepareCryptTable()
{
	unsigned int seed = 0x00100001;
	for( unsigned int index1 = 0; index1 < 0x100; index1++ ){
		for( unsigned int index2 = index1, i = 0; i < 5; i++, index2 += 0x100 ){
			seed = (seed * 125 + 3) % 0x2AAAAB;
			unsigned int temp1 = (seed & 0xFFFF) << 0x10;
			seed = (seed * 125 + 3) % 0x2AAAAB;
			unsigned int temp2 = (seed & 0xFFFF);
			CryptTable[index2] = temp1 | temp2;
		}
	}
}

static unsigned int HashString(const char* str, unsigned int hashType)
{
	unsigned int seed1 = 0x7FED7FED;
	unsigned int seed2 = 0xEEEEEEEE;
	while( *str ){
		unsigned int ch = (unsigned char)toupper(*str++);
		if( ch == '/' ) ch = '\\';
		seed1 = CryptTable[hashType * 0x100 + ch] ^ (seed1 + seed2);
		seed2 = ch + seed1 + seed2 + (seed2 << 5) + 3;
	}
	return seed1;
}

static void DecryptBlock(void* block, unsigned int length, unsigned int key)
{
	unsigned int* buffer = (unsigned int*)block;
	unsigned int seed = 0xEEEEEEEE;
	for( length >>= 2; length; length-- ){
		seed += CryptTable[0x400 + (key & 0xFF)];
		unsigned int ch = *buffer ^ (key + seed);
		key = ((~key << 0x15) + 0x11111111) | (key >> 0x0B);
		seed = ch + seed + (seed << 5) + 3;
		*buffer++ = ch;
	}
}

//-----------------------------------------------------------------------------
// pklib explode() plumbing: it pulls/pushes through callbacks

struct ExplodeBuffers
{
	const unsigned char* in;
	unsigned int inSize;
	unsigned int inPos;
	unsigned char* out;
	unsigned int outSize;
	unsigned int outPos;
};

static unsigned int ExplodeRead(char* buf, unsigned int* size, void* param)
{
	ExplodeBuffers* b = (ExplodeBuffers*)param;
	unsigned int avail = b->inSize - b->inPos;
	unsigned int want = *size < avail ? *size : avail;
	memcpy(buf, b->in + b->inPos, want);
	b->inPos += want;
	return want;
}

static void ExplodeWrite(char* buf, unsigned int* size, void* param)
{
	ExplodeBuffers* b = (ExplodeBuffers*)param;
	unsigned int avail = b->outSize - b->outPos;
	unsigned int want = *size < avail ? *size : avail;
	memcpy(b->out + b->outPos, buf, want);
	b->outPos += want;
}

static bool Explode(const unsigned char* in, unsigned int inSize, unsigned char* out, unsigned int outSize)
{
	ExplodeBuffers b = { in, inSize, 0, out, outSize, 0 };
	TDcmpStruct* work = (TDcmpStruct*)malloc(sizeof(TDcmpStruct));
	unsigned int err = explode(ExplodeRead, ExplodeWrite, work, &b);
	free(work);
	return err == CMP_NO_ERROR && b.outPos == outSize;
}

//-----------------------------------------------------------------------------
// MPQ reading

#pragma pack(push, 1)
struct MpqHeader
{
	unsigned int  signature;     // 'MPQ\x1A'
	unsigned int  headerSize;
	unsigned int  archiveSize;
	unsigned short formatVersion;
	unsigned short blockSizeShift;
	unsigned int  hashTablePos;
	unsigned int  blockTablePos;
	unsigned int  hashTableSize;
	unsigned int  blockTableSize;
};
struct MpqHash  { unsigned int name1, name2; unsigned short locale, platform; unsigned int blockIndex; };
struct MpqBlock { unsigned int filePos, cSize, fSize, flags; };
#pragma pack(pop)

#define MPQ_FILE_IMPLODE     0x00000100
#define MPQ_FILE_COMPRESS    0x00000200
#define MPQ_FILE_ENCRYPTED   0x00010000
#define MPQ_FILE_FIXSEED     0x00020000
#define MPQ_FILE_SINGLE_UNIT 0x01000000
#define MPQ_FILE_EXISTS      0x80000000
#define HASH_ENTRY_FREE      0xFFFFFFFF

struct Mpq
{
	FILE* file;
	MpqHeader hdr;
	MpqHash* hashTable;
	MpqBlock* blockTable;
	unsigned int sectorSize;
};

static bool MpqOpen(Mpq& mpq, const char* path)
{
	memset(&mpq, 0, sizeof(mpq));
	mpq.file = fopen(path, "rb");
	if( !mpq.file ) return false;
	if( fread(&mpq.hdr, 1, sizeof(MpqHeader), mpq.file) != sizeof(MpqHeader) ) return false;
	if( mpq.hdr.signature != 0x1A51504D ) return false;
	mpq.sectorSize = 512 << mpq.hdr.blockSizeShift;

	unsigned int hashBytes = mpq.hdr.hashTableSize * sizeof(MpqHash);
	unsigned int blockBytes = mpq.hdr.blockTableSize * sizeof(MpqBlock);
	mpq.hashTable = (MpqHash*)malloc(hashBytes);
	mpq.blockTable = (MpqBlock*)malloc(blockBytes);
	fseek(mpq.file, mpq.hdr.hashTablePos, SEEK_SET);
	if( fread(mpq.hashTable, 1, hashBytes, mpq.file) != hashBytes ) return false;
	fseek(mpq.file, mpq.hdr.blockTablePos, SEEK_SET);
	if( fread(mpq.blockTable, 1, blockBytes, mpq.file) != blockBytes ) return false;
	DecryptBlock(mpq.hashTable, hashBytes, HashString("(hash table)", 3));
	DecryptBlock(mpq.blockTable, blockBytes, HashString("(block table)", 3));
	return true;
}

static const MpqBlock* MpqFindFile(const Mpq& mpq, const char* name)
{
	unsigned int start = HashString(name, 0) & (mpq.hdr.hashTableSize - 1);
	unsigned int name1 = HashString(name, 1);
	unsigned int name2 = HashString(name, 2);
	for( unsigned int i = 0, index = start; i < mpq.hdr.hashTableSize; i++, index = (index + 1) & (mpq.hdr.hashTableSize - 1) ){
		const MpqHash& h = mpq.hashTable[index];
		if( h.blockIndex == HASH_ENTRY_FREE ) return 0;
		if( h.name1 == name1 && h.name2 == name2 && h.blockIndex < mpq.hdr.blockTableSize )
			return &mpq.blockTable[h.blockIndex];
	}
	return 0;
}

static const char* BaseName(const char* path)
{
	const char* slash = strrchr(path, '\\');
	return slash ? slash + 1 : path;
}

// returns malloc'ed buffer of block->fSize bytes, or 0
static unsigned char* MpqReadFile(Mpq& mpq, const char* name, const MpqBlock* block)
{
	if( !(block->flags & MPQ_FILE_EXISTS) ) return 0;
	unsigned char* out = (unsigned char*)malloc(block->fSize ? block->fSize : 1);

	unsigned int key = 0;
	if( block->flags & MPQ_FILE_ENCRYPTED ){
		key = HashString(BaseName(name), 3);
		if( block->flags & MPQ_FILE_FIXSEED )
			key = (key + block->filePos) ^ block->fSize;
	}
	bool compressed = (block->flags & (MPQ_FILE_IMPLODE | MPQ_FILE_COMPRESS)) != 0;

	if( !compressed || (block->flags & MPQ_FILE_SINGLE_UNIT) ){
		unsigned char* raw = (unsigned char*)malloc(block->cSize ? block->cSize : 1);
		fseek(mpq.file, block->filePos, SEEK_SET);
		if( fread(raw, 1, block->cSize, mpq.file) != block->cSize ){ free(raw); free(out); return 0; }
		if( block->flags & MPQ_FILE_ENCRYPTED ) DecryptBlock(raw, block->cSize, key);
		if( !compressed || block->cSize == block->fSize ){
			memcpy(out, raw, block->fSize < block->cSize ? block->fSize : block->cSize);
		}else{
			const unsigned char* src = raw;
			unsigned int srcLen = block->cSize;
			if( block->flags & MPQ_FILE_COMPRESS ){ src++; srcLen--; } // multi-compression mask byte
			if( !Explode(src, srcLen, out, block->fSize) ){ free(raw); free(out); return 0; }
		}
		free(raw);
		return out;
	}

	unsigned int sectorCount = (block->fSize + mpq.sectorSize - 1) / mpq.sectorSize;
	unsigned int offsetBytes = (sectorCount + 1) * sizeof(unsigned int);
	unsigned int* offsets = (unsigned int*)malloc(offsetBytes);
	fseek(mpq.file, block->filePos, SEEK_SET);
	if( fread(offsets, 1, offsetBytes, mpq.file) != offsetBytes ){ free(offsets); free(out); return 0; }
	if( block->flags & MPQ_FILE_ENCRYPTED ) DecryptBlock(offsets, offsetBytes, key - 1);

	for( unsigned int i = 0; i < sectorCount; i++ ){
		unsigned int rawLen = offsets[i + 1] - offsets[i];
		unsigned int plainLen = block->fSize - i * mpq.sectorSize;
		if( plainLen > mpq.sectorSize ) plainLen = mpq.sectorSize;
		unsigned char* raw = (unsigned char*)malloc(rawLen ? rawLen : 1);
		fseek(mpq.file, block->filePos + offsets[i], SEEK_SET);
		if( fread(raw, 1, rawLen, mpq.file) != rawLen ){ free(raw); free(offsets); free(out); return 0; }
		if( block->flags & MPQ_FILE_ENCRYPTED ) DecryptBlock(raw, rawLen, key + i);
		if( rawLen == plainLen ){
			memcpy(out + i * mpq.sectorSize, raw, plainLen);
		}else{
			const unsigned char* src = raw;
			unsigned int srcLen = rawLen;
			if( block->flags & MPQ_FILE_COMPRESS ){ src++; srcLen--; }
			if( !Explode(src, srcLen, out + i * mpq.sectorSize, plainLen) ){
				free(raw); free(offsets); free(out); return 0;
			}
		}
		free(raw);
	}
	free(offsets);
	return out;
}

int main(int argc, char** argv)
{
	if( argc < 4 ){
		printf("usage: mpq_extract <archive.mpq> <outdir> <file-in-mpq> [more files...]\n");
		return 1;
	}
	PrepareCryptTable();
	Mpq mpq;
	if( !MpqOpen(mpq, argv[1]) ){
		printf("FAIL open archive %s\n", argv[1]);
		return 2;
	}
	int failed = 0;
	for( int i = 3; i < argc; i++ ){
		const MpqBlock* block = MpqFindFile(mpq, argv[i]);
		if( !block ){
			printf("MISS %s\n", argv[i]);
			failed++;
			continue;
		}
		unsigned char* data = MpqReadFile(mpq, argv[i], block);
		if( !data ){
			printf("FAIL read %s (flags %08X)\n", argv[i], block->flags);
			failed++;
			continue;
		}
		char out[MAX_PATH];
		sprintf(out, "%s\\%s", argv[2], BaseName(argv[i]));
		FILE* f = fopen(out, "wb");
		if( !f ){
			printf("FAIL write %s\n", out);
			failed++;
		}else{
			fwrite(data, 1, block->fSize, f);
			fclose(f);
			printf("OK   %s -> %s (%u bytes, flags %08X)\n", argv[i], out, block->fSize, block->flags);
		}
		free(data);
	}
	fclose(mpq.file);
	return failed ? 3 : 0;
}
