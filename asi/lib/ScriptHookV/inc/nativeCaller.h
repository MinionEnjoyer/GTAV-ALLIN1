/*
	THIS FILE IS A PART OF GTA V SCRIPT HOOK SDK
				http://dev-c.com
			(C) Alexander Blade 2015-2024
*/

#pragma once

#include "main.h"

template <typename T>
static inline void nativePush(T val) {
	static_assert(sizeof(T) <= sizeof(UINT64), "Type too large for native push");
	UINT64 val64 = 0;
	*reinterpret_cast<T*>(&val64) = val;
	nativePush64(val64);
}

// invoke with 0 to 16 parameters

template <typename R>
static inline R invoke(UINT64 hash) {
	nativeInit(hash);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1>
static inline R invoke(UINT64 hash, T1 p1) {
	nativeInit(hash);
	nativePush(p1);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2>
static inline R invoke(UINT64 hash, T1 p1, T2 p2) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3, typename T4>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3, T4 p4) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	nativePush(p4);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3, typename T4, typename T5>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3, T4 p4, T5 p5) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	nativePush(p4);
	nativePush(p5);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3, typename T4, typename T5, typename T6>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3, T4 p4, T5 p5, T6 p6) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	nativePush(p4);
	nativePush(p5);
	nativePush(p6);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3, typename T4, typename T5, typename T6, typename T7>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3, T4 p4, T5 p5, T6 p6, T7 p7) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	nativePush(p4);
	nativePush(p5);
	nativePush(p6);
	nativePush(p7);
	return *reinterpret_cast<R*>(nativeCall());
}

template <typename R, typename T1, typename T2, typename T3, typename T4, typename T5, typename T6, typename T7, typename T8>
static inline R invoke(UINT64 hash, T1 p1, T2 p2, T3 p3, T4 p4, T5 p5, T6 p6, T7 p7, T8 p8) {
	nativeInit(hash);
	nativePush(p1);
	nativePush(p2);
	nativePush(p3);
	nativePush(p4);
	nativePush(p5);
	nativePush(p6);
	nativePush(p7);
	nativePush(p8);
	return *reinterpret_cast<R*>(nativeCall());
}


