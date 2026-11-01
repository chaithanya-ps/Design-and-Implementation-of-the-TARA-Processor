# TARA RAM images - expected results

All images load at word address 0 (byte address 0). Run until the CPU halts (TSTATE frozen, IR_OUT = 0800).
PC_COUNT at halt = address of the HLT + 2. Registers are listed R0..R7, hex. Cycles = clock ticks from reset to halt.
Expected values come from a software model that executes the real control ROM from G06_th6_microcode_gen.py.

## Binary_search  - search 7 in {1,3,5,7,9,11}
- file: `Binary_search.hex`, 39 instruction words, 307 cycles
- final registers: R0=0400 R1=0006 R2=0007 R3=0003 R4=0003 R5=0003 R6=0003 R7=0000
- HLT addresses in program: 004C (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x0405 = 01 03 05 07 09 0B (written by the program itself)

## GCD  - gcd(48,18)
- file: `GCD.hex`, 11 instruction words, 128 cycles
- final registers: R0=0000 R1=0006 R2=0006 R3=0006 R4=0000 R5=0000 R6=0000 R7=0000
- HLT addresses in program: 0014 (PC_COUNT shows that address + 2 at halt)

## Linear Search  - search 9 in {5,8,1,9,3,7}
- file: `Linear Search.hex`, 29 instruction words, 257 cycles
- final registers: R0=0400 R1=0006 R2=0009 R3=0003 R4=FFFD R5=0403 R6=0000 R7=0000
- HLT addresses in program: 0036, 0038 (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x0405 = 05 08 01 09 03 07 (written by the program itself)

## bubble_sort  - sort 256 bytes at 0x0400
- file: `bubble_sort.hex`, 25 instruction words, 1828671 cycles
- final registers: R0=0400 R1=0100 R2=0000 R3=0000 R4=0401 R5=0000 R6=0000 R7=0000
- HLT addresses in program: 0030 (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x04FF must be the 256 input bytes sorted ascending (input and expected output below)

## collatz_step  - Collatz steps for n=7
- file: `collatz_step.hex`, 17 instruction words, 777 cycles
- final registers: R0=0000 R1=0001 R2=0010 R3=0001 R4=0000 R5=0000 R6=0005 R7=0000
- HLT addresses in program: 0020 (PC_COUNT shows that address + 2 at halt)

## count_set_bits  - popcount of 0xB3B5
- file: `count_set_bits.hex`, 11 instruction words, 508 cycles
- final registers: R0=0000 R1=0000 R2=000A R3=0001 R4=0001 R5=0000 R6=0000 R7=0000
- HLT addresses in program: 0014 (PC_COUNT shows that address + 2 at halt)

## fibonacci  - F(10)
- file: `fibonacci.hex`, 11 instruction words, 326 cycles
- final registers: R0=0000 R1=0000 R2=0037 R3=0059 R4=0059 R5=0000 R6=0037 R7=0000
- HLT addresses in program: 0014 (PC_COUNT shows that address + 2 at halt)

## first_N_primes  - first 10 primes to 0x0400
- file: `first_N_primes.hex`, 23 instruction words, 16529 cycles
- final registers: R0=0400 R1=0000 R2=040A R3=001D R4=001D R5=FFE5 R6=0000 R7=0000
- HLT addresses in program: 002C (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x0409 = 02 03 05 07 0B 0D 11 13 17 1D

## power_of_two  - 2^10
- file: `power_of_two.hex`, 7 instruction words, 217 cycles
- final registers: R0=0000 R1=0000 R2=0400 R3=0000 R4=0000 R5=0000 R6=0000 R7=0000
- HLT addresses in program: 000C (PC_COUNT shows that address + 2 at halt)

## prime_test  - is 17 prime
- file: `prime_test.hex`, 18 instruction words, 1560 cycles
- final registers: R0=0000 R1=0011 R2=0001 R3=0011 R4=FFF1 R5=0000 R6=0002 R7=0000
- HLT addresses in program: 001E, 0022 (PC_COUNT shows that address + 2 at halt)

## rev_arr  - reverse 256 bytes at 0x0400
- file: `rev_arr.hex`, 18 instruction words, 7731 cycles
- final registers: R0=0400 R1=0100 R2=0480 R3=047F R4=FFFF R5=00B5 R6=0079 R7=0000
- HLT addresses in program: 0022 (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x04FF must be the input bytes in reverse order

## selection_sort  - sort 256 bytes at 0x0400
- file: `selection_sort.hex`, 28 instruction words, 1619838 cycles
- final registers: R0=0400 R1=0100 R2=0500 R3=04FF R4=0500 R5=00FF R6=0500 R7=0000
- HLT addresses in program: 0036 (PC_COUNT shows that address + 2 at halt)
- memory 0x0400..0x04FF must be the 256 input bytes sorted ascending (input and expected output below)

## sum_1toN  - 1+...+10
- file: `sum_1toN.hex`, 7 instruction words, 217 cycles
- final registers: R0=0000 R1=0000 R2=0037 R3=0000 R4=0000 R5=0000 R6=0000 R7=0000
- HLT addresses in program: 000C (PC_COUNT shows that address + 2 at halt)

## Array data for bubble_sort, selection_sort, rev_arr (preloaded in the .hex at 0x0400..0x04FF)

input bytes (address 0x0400 first, 16 per row):
    F0 DC 9A 00 27 61 4B 36 62 50 80 79 92 C2 A1 E0
    2F F7 7D 94 49 FE CE 00 44 9C FB B6 F6 6D 4F B0
    1D 94 4F 24 4A 9C 2C A7 DE 62 03 0F 4C D8 19 77
    8E C3 68 8A 1C FB 37 E3 85 C8 EC 36 2F A3 D9 F4
    99 49 EB 5B 15 0D 14 81 7E BF FA 9D 8B 82 E2 8A
    02 03 D0 A2 16 70 13 E9 D9 B4 6A F9 75 69 40 58
    C7 93 F3 F2 E5 C0 D1 C2 62 DB F2 42 4D CD 07 E9
    E2 A7 0E 0E 7B 44 FC 7D 35 56 65 AA B8 3C C4 B5
    79 70 CE 2D DA 38 AF 38 E3 8D 45 2B B7 FD D8 E8
    BD AF C9 77 B6 3C 68 B1 F3 F7 1D 23 17 17 4F FB
    AD 9A 92 DE 72 44 FB DB E8 57 D7 96 52 D4 BF 8B
    0E B1 EE 55 FC 8E B5 C4 74 FB CE CF E7 7B 14 1F
    98 23 87 8B B7 87 1F 3A 80 32 0D 4A F2 AE 8E 8D
    82 D3 35 1B 85 C8 EE 9E 65 12 8D 61 7A E8 6F 0D
    83 71 57 02 F9 48 5A CC 53 AC 03 4A 33 48 15 52
    C9 A1 AD AD 4B 5F 83 C3 EA 87 FF 84 4B 4B 2A 4C

sorted output (bubble_sort, selection_sort):
    00 00 02 02 03 03 03 07 0D 0D 0D 0E 0E 0E 0F 12
    13 14 14 15 15 16 17 17 19 1B 1C 1D 1D 1F 1F 23
    23 24 27 2A 2B 2C 2D 2F 2F 32 33 35 35 36 36 37
    38 38 3A 3C 3C 40 42 44 44 44 45 48 48 49 49 4A
    4A 4A 4B 4B 4B 4B 4C 4C 4D 4F 4F 4F 50 52 52 53
    55 56 57 57 58 5A 5B 5F 61 61 62 62 62 65 65 68
    68 69 6A 6D 6F 70 70 71 72 74 75 77 77 79 79 7A
    7B 7B 7D 7D 7E 80 80 81 82 82 83 83 84 85 85 87
    87 87 8A 8A 8B 8B 8B 8D 8D 8D 8E 8E 8E 92 92 93
    94 94 96 98 99 9A 9A 9C 9C 9D 9E A1 A1 A2 A3 A7
    A7 AA AC AD AD AD AE AF AF B0 B1 B1 B4 B5 B5 B6
    B6 B7 B7 B8 BD BF BF C0 C2 C2 C3 C3 C4 C4 C7 C8
    C8 C9 C9 CC CD CE CE CE CF D0 D1 D3 D4 D7 D8 D8
    D9 D9 DA DB DB DC DE DE E0 E2 E2 E3 E3 E5 E7 E8
    E8 E8 E9 E9 EA EB EC EE EE F0 F2 F2 F2 F3 F3 F4
    F6 F7 F7 F9 F9 FA FB FB FB FB FB FC FC FD FE FF

reversed output (rev_arr):
    4C 2A 4B 4B 84 FF 87 EA C3 83 5F 4B AD AD A1 C9
    52 15 48 33 4A 03 AC 53 CC 5A 48 F9 02 57 71 83
    0D 6F E8 7A 61 8D 12 65 9E EE C8 85 1B 35 D3 82
    8D 8E AE F2 4A 0D 32 80 3A 1F 87 B7 8B 87 23 98
    1F 14 7B E7 CF CE FB 74 C4 B5 8E FC 55 EE B1 0E
    8B BF D4 52 96 D7 57 E8 DB FB 44 72 DE 92 9A AD
    FB 4F 17 17 23 1D F7 F3 B1 68 3C B6 77 C9 AF BD
    E8 D8 FD B7 2B 45 8D E3 38 AF 38 DA 2D CE 70 79
    B5 C4 3C B8 AA 65 56 35 7D FC 44 7B 0E 0E A7 E2
    E9 07 CD 4D 42 F2 DB 62 C2 D1 C0 E5 F2 F3 93 C7
    58 40 69 75 F9 6A B4 D9 E9 13 70 16 A2 D0 03 02
    8A E2 82 8B 9D FA BF 7E 81 14 0D 15 5B EB 49 99
    F4 D9 A3 2F 36 EC C8 85 E3 37 FB 1C 8A 68 C3 8E
    77 19 D8 4C 0F 03 62 DE A7 2C 9C 4A 24 4F 94 1D
    B0 4F 6D F6 B6 FB 9C 44 00 CE FE 49 94 7D F7 2F
    E0 A1 C2 92 79 80 50 62 36 4B 61 27 00 9A DC F0

# Quick variants (N = 16 instead of 256) - same program, only the two N-setting lines changed

## bubble_sort_N16  - quick variant, N=16
- file: `bubble_sort_N16.hex`, 25 instruction words, 6816 cycles
- final registers: R0=0400 R1=0010 R2=0000 R3=0000 R4=0401 R5=0000 R6=0027 R7=FFD9
- HLT addresses in program: 0030 (PC_COUNT shows that address + 2 at halt)
- input  0x0400..0x040F = F0 DC 9A 00 27 61 4B 36 62 50 80 79 92 C2 A1 E0
- output 0x0400..0x040F = 00 27 36 4B 50 61 62 79 80 92 9A A1 C2 DC E0 F0

## selection_sort_N16  - quick variant, N=16
- file: `selection_sort_N16.hex`, 28 instruction words, 7169 cycles
- final registers: R0=0400 R1=0010 R2=0410 R3=040F R4=0410 R5=00F0 R6=0410 R7=0000
- HLT addresses in program: 0036 (PC_COUNT shows that address + 2 at halt)
- input  0x0400..0x040F = F0 DC 9A 00 27 61 4B 36 62 50 80 79 92 C2 A1 E0
- output 0x0400..0x040F = 00 27 36 4B 50 61 62 79 80 92 9A A1 C2 DC E0 F0

## rev_arr_N16  - quick variant, N=16
- file: `rev_arr_N16.hex`, 18 instruction words, 531 cycles
- final registers: R0=0400 R1=0010 R2=0408 R3=0407 R4=FFFF R5=0036 R6=0062 R7=0000
- HLT addresses in program: 0022 (PC_COUNT shows that address + 2 at halt)
- input  0x0400..0x040F = F0 DC 9A 00 27 61 4B 36 62 50 80 79 92 C2 A1 E0
- output 0x0400..0x040F = E0 A1 C2 92 79 80 50 62 36 4B 61 27 00 9A DC F0

