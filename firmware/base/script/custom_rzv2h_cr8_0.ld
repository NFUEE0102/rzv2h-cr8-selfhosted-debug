/*
                  Linker File for Renesas FSP
*/

INCLUDE memory_regions.ld

/* Custom Definition */
/* Change these definitions if you want to change the memory area to suit your board specifications or software design. */
/* Offset from the start address of the SRAM area allocated to Cortex-R8 */
/* For multi-core configuration, the areas to be allocated to both core0 and core1 are defined */
SRAM_CR8_0_CUSTOM_OFFSET = 0x08180000;
SRAM_CR8_1_CUSTOM_OFFSET = 0x081C0000;
/* Length of cache-enabled SRAM area  to be allocated to Cortex-R8 */
SRAM_CR8_0_CACHE_CUSTOM_LENGTH = 0x00020000;
SRAM_CR8_1_CACHE_CUSTOM_LENGTH = 0x00020000;
/* Length of cache-disabled SRAM area  to be allocated to Cortex-R8, this area is placed immediately after the cache-enabled area */
/* The last 4 bytes are allocated for arbitration of initialization between multiple cores */
SRAM_CR8_0_UNCACHE_CUSTOM_LENGTH = 0x00020000;
SRAM_CR8_1_UNCACHE_CUSTOM_LENGTH = 0x00020000;
/* Offset from the start address of the xSPI area allocated to Cortex-R8 */
XSPIFLASH_CUSTOM_OFFSET = 0x00000000;
/* Length of xSPI area  to be allocated to Cortex-R8 */
XSPIFLASH_CUSTOM_LENGTH = 0x10000000;
/* Offset from the start address of the DDR0 area allocated to Cortex-R8 */
DDR0_CUSTOM_OFFSET = 0x00800000;
/* Length of cache-enabled DDR0 area  to be allocated to Cortex-R8 */
DDR0_CACHE_CUSTOM_LENGTH = 0x00800000;
/* Length of cache-disabled DDR0 area  to be allocated to Cortex-R8, this area is placed immediately after the cache-enabled area */
DDR0_UNCACHE_CUSTOM_LENGTH = 0x00800000;
/* The offset of the header placed in flash memory to allow the main core to load the FSP program run by the Cortex-R8 */
FLASH_HEADER_CUSTOM_OFFSET = 0x00200000;

/* Memory Map Definition */
ITCM_PRV_START          = DEFINED(ITCM_AXI_CR8_0_START) ? ITCM_AXI_CR8_0_START - 0x12040000 : 0;
ITCM_PRV_LENGTH         = 0x0001FE00;
DTCM_PRV_START          = DEFINED(ITCM_AXI_CR8_0_START) ? ITCM_AXI_CR8_0_START - 0x12020000 : 0;
DTCM_PRV_LENGTH         = 0x00020000;
ITCM_PRV_AXI_START      = DEFINED(ITCM_AXI_CR8_0_START) ? ITCM_AXI_CR8_0_START : 0;
SRAM_CR8_0_PRV_START    = DEFINED(SRAM_CR8_0_START) ? SRAM_CR8_0_START + SRAM_CR8_0_CUSTOM_OFFSET : 0;
SRAM_CR8_1_PRV_START    = DEFINED(SRAM_CR8_0_START) ? SRAM_CR8_0_START + SRAM_CR8_1_CUSTOM_OFFSET : 0;
SRAM_CACHE_PRV_START    = SRAM_CR8_0_PRV_START;
SRAM_CACHE_PRV_LENGTH   = SRAM_CR8_0_CACHE_CUSTOM_LENGTH;
SRAM_UNCACHE_PRV_START  = SRAM_CR8_0_PRV_START + SRAM_CR8_0_CACHE_CUSTOM_LENGTH;
SRAM_UNCACHE_PRV_LENGTH = SRAM_CR8_0_UNCACHE_CUSTOM_LENGTH - 0x04;
XSPIFLASH_PRV_START     = DEFINED(XSPIFLASH_CR8_0_START) ? XSPIFLASH_CR8_0_START + XSPIFLASH_CUSTOM_OFFSET : 0;
XSPIFLASH_PRV_LENGTH    = XSPIFLASH_CUSTOM_LENGTH;
DDR_CACHE_PRV_START     = DEFINED(DDR0_CR8_0_START) ? DDR0_CR8_0_START + DDR0_CUSTOM_OFFSET : 0;
DDR_CACHE_PRV_LENGTH    = DDR0_CACHE_CUSTOM_LENGTH;
DDR_UNCACHE_PRV_START   = DEFINED(DDR0_CR8_0_START) ? DDR0_CR8_0_START + DDR0_CUSTOM_OFFSET + DDR0_CACHE_CUSTOM_LENGTH : 0;
DDR_UNCACHE_PRV_LENGTH  = DDR0_UNCACHE_CUSTOM_LENGTH;

/* Memory allocation OpenAMP using ddr. */
OPENAMP_RSCTBL_START    = DEFINED(DDR0_CR8_0_START) ? DDR0_CR8_0_START + 0x02F02000 : 0;
OPENAMP_RSCTBL_LENGTH   = 0x00001000;
MHU_SHMEM_START         = DEFINED(DDR0_CR8_0_START) ? DDR0_CR8_0_START + 0x02F01000 : 0;
MHU_SHMEM_LENGTH        = 0x00001000;
OPENAMP_VRING_START     = DEFINED(DDR0_CR8_0_START) ? DDR0_CR8_0_START + 0x03800000 : 0;
OPENAMP_VRING_LENGTH    = 0x00800000;

/* Flash header infomation */
ITCM_HEADER_START  = ITCM_PRV_LENGTH == 0 ? 0 : ITCM_PRV_START + ITCM_PRV_LENGTH;
FLASH_HEADER_START =  DEFINED(XSPIFLASH_CR8_0_START) ? XSPIFLASH_CR8_0_START + FLASH_HEADER_CUSTOM_OFFSET : 0;
HEADER_LENGTH      = 0x80;
FLASH_DATA_START   = FLASH_HEADER_START + HEADER_LENGTH;

/* Initialization waiting area, allocated last 4byte on SRAM */
INIT_WAIT_AREA_LENGTH = 0x00000004;
INIT_WAIT_AREA_START = SRAM_CR8_0_PRV_START + SRAM_CR8_0_CACHE_CUSTOM_LENGTH + SRAM_CR8_0_UNCACHE_CUSTOM_LENGTH - INIT_WAIT_AREA_LENGTH;
INIT_WAIT_AREA_OTHER_CORE_START = SRAM_CR8_1_PRV_START + SRAM_CR8_1_CACHE_CUSTOM_LENGTH + SRAM_CR8_1_UNCACHE_CUSTOM_LENGTH - INIT_WAIT_AREA_LENGTH;

/* Dummy area to provide a space between the code area and data area */
DUMMY_START = ITCM_PRV_LENGTH == 0 ? 0 : ITCM_PRV_START + ITCM_PRV_LENGTH - 0x10;
DUMMY_LENGTH = 0x00000008;

MEMORY
{
    ITCM : ORIGIN = ITCM_PRV_START, LENGTH = ITCM_PRV_LENGTH
    DTCM : ORIGIN = DTCM_PRV_START, LENGTH = DTCM_PRV_LENGTH
    SRAM_CACHE : ORIGIN = SRAM_CACHE_PRV_START, LENGTH = SRAM_CACHE_PRV_LENGTH
    SRAM_UNCACHE : ORIGIN = SRAM_UNCACHE_PRV_START, LENGTH = SRAM_UNCACHE_PRV_LENGTH
    XSPI_FLASH : ORIGIN = XSPIFLASH_PRV_START, LENGTH = XSPIFLASH_PRV_LENGTH
    DDR_SDRAM_CACHE : ORIGIN = DDR_CACHE_PRV_START, LENGTH = DDR_CACHE_PRV_LENGTH
    DDR_SDRAM_UNCACHE : ORIGIN = DDR_UNCACHE_PRV_START, LENGTH = DDR_UNCACHE_PRV_LENGTH

    OPENAMP_RSCTBL(rw): ORIGIN = OPENAMP_RSCTBL_START,LENGTH = OPENAMP_RSCTBL_LENGTH
    MHU_SHMEM(rw)     : ORIGIN = MHU_SHMEM_START,     LENGTH = MHU_SHMEM_LENGTH
    OPENAMP_VRING(rw) : ORIGIN = OPENAMP_VRING_START, LENGTH = OPENAMP_VRING_LENGTH

    HEADER_REGION(r) : ORIGIN = ITCM_HEADER_START, LENGTH = HEADER_LENGTH

    INIT_WAIT_AREA(rw) : ORIGIN = INIT_WAIT_AREA_START, LENGTH = INIT_WAIT_AREA_LENGTH
    INIT_WAIT_AREA_OTHER_CORE(rw) : ORIGIN = INIT_WAIT_AREA_OTHER_CORE_START, LENGTH = INIT_WAIT_AREA_LENGTH

    DUMMY : ORIGIN = DUMMY_START, LENGTH = DUMMY_LENGTH
}

ENTRY(Reset_Handler)
SECTIONS
{
    .itcm_load_section0 0x00000000 :
    {
        _itcm_load_start = .;
        /* vector */
        _fvector_start = .;
        KEEP(*(.intvec))
        _fvector_end = .;

        . = ALIGN(0x100);

        /* BSP code */
        _text_start = .;

        KEEP(*(.int_handler))

        ./rzv_gen/*.o(.text*)
        ./rzv/fsp/*.o(.text*)
        ./rzv/board/*.o(.text*)

        KEEP(*(.init))
        KEEP(*(.fini))

        /* .ctors */
        *crtbegin.o(.ctors)
        *crtbegin?.o(.ctors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .ctors)
        *(SORT(.ctors.*))
        *(.ctors)
        _ctor_end = .;

        /* .dtors */
        *crtbegin.o(.dtors)
        *crtbegin?.o(.dtors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .dtors)
        *(SORT(.dtors.*))
        *(.dtors)
        _dtor_end = .;

        KEEP(*(.warm_start))

        KEEP(*(.eh_frame*))

        . = ALIGN(0x04);
        *(.ARM.extab* .gnu.linkonce.armextab.*)

        . = ALIGN(0x04);
        __exidx_start = .;
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
        __exidx_end = .;

        . = ALIGN(0x04);
        *(.got)
        *(.got.plt)
        _text_end = .;
    } > ITCM
    .loader_dummy_itcm :
    {
        _loader_dummy_itcm_start = .;
        KEEP(*(.loader_dummy_itcm));
        _loader_dummy_itcm_end = .;
    } > DUMMY AT > ITCM
    .itcm_load_section1 :
    {
        . = ALIGN(0x10);
        /* BSP data */
        _data_start = .;

        *(vtable)
        KEEP(*(.application_vectors))
        ./rzv_gen/*.o(.data*)
        ./rzv/fsp/*.o(.data*)
        ./rzv/board/*.o(.data*)

        ./rzv_gen/*.o(.rodata*)
        ./rzv/fsp/*.o(.rodata*)
        ./rzv/board/*.o(.rodata*)
        _erodata = .;

        . = ALIGN(0x04);
        /* preinit data */
        PROVIDE_HIDDEN (__preinit_array_start = .);
        KEEP(*(.preinit_array))
        PROVIDE_HIDDEN (__preinit_array_end = .);

        . = ALIGN(0x04);
        /* init data */
        PROVIDE_HIDDEN (__init_array_start = .);
        KEEP(*(SORT(.init_array.*)))
        KEEP(*(.init_array))
        PROVIDE_HIDDEN (__init_array_end = .);

        . = ALIGN(0x04);
        /* finit data */
        PROVIDE_HIDDEN (__fini_array_start = .);
        KEEP(*(SORT(.fini_array.*)))
        KEEP(*(.fini_array))
        PROVIDE_HIDDEN (__fini_array_end = .);

        KEEP(*(.jcr*))

        . = ALIGN(0x04);

        /* All data end */
        _data_end = .;
        _itcm_load_end = .;
    } > ITCM
    /* ---------------------------------------------------------------------
     * FreeRTOS heap 放 DDR(2026-08-24)
     *
     * ucHeap 原本被下面 .dtcm_noload_section 的 `./rzv/fsp/*.o(.bss*)` 抓進
     * DTCM(它在 rm_freertos_port/cr/port.o 的 .bss.ucHeap)。DTCM 只有 128 KB,
     * 而且已被 g_heap(32 KB)、六個模式堆疊(各 4 KB)、gp_renesas_isr_context
     * 吃掉大半 —— 加上 64 KB 的 ucHeap 之後只剩 4,316 bytes。
     *
     * 實測後果:data abort,DFAR = 0x0005AFB4,落在所有已映射區域之外
     * (DTCM 到 0x3FFFF 為止)。而 startup.asm 的預設 abort handler 是
     * `b <self>` 無窮迴圈、abort mode 又遮蔽 IRQ,所以表現成「整顆 R8 突然
     * 死掉、所有 task 同時凍結、沒有任何 FreeRTOS hook 觸發」——
     * 完全指不到根因。
     *
     * Renesas 官方的 rzv2h_drone_px4 就是把 heap 放 DDR(8 MB)。
     * 我們的 DDR_SDRAM_CACHE 有 8 MB(0x40800000,原本只用了 80 bytes)。
     *
     * ⚠️ 這一段**必須排在 .dtcm_noload_section 之前** —— GNU ld 是先到先得,
     *    排在後面的話 ucHeap 還是會被 ./rzv/fsp/*.o(.bss*) 那條抓走。
     *    (第一次改就是插錯位置,DTCM 溢出 978,724 bytes。)
     *
     * ⚠️ 符號名不能用 __HeapBase/__HeapLimit —— 那兩個已經被下面的
     *    STD heap 用了。
     * --------------------------------------------------------------------- */
    .rtos_heap_section (NOLOAD) : ALIGN(8)
    {
        . = ALIGN(8);
        __RTOSHeapBase = .;
        KEEP(*(.freertos_heap))
        KEEP(*(.freertos_heap.*))
        KEEP(*(.bss.ucHeap))
        . = ALIGN(8);
        __RTOSHeapLimit = .;
    } > DDR_SDRAM_CACHE

    .dtcm_noload_section (NOLOAD) :
    {
        /* heap */
        . = ALIGN(8);
        __HeapBase = .;
        /* Place the STD heap here. */
        KEEP(*(.heap))
        __HeapLimit = .;

        /* system stack */
        . = ALIGN(8);
        __SysStackBase = .;
        /* Place the sys_stack here. */
        KEEP(*(.sys_stack))
        __SysStackLimit = .;

        /* SVC stack */
        . = ALIGN(8);
        __SvcStackBase = .;
        /* Place the svc_stack here. */
        KEEP(*(.svc_stack))
        __SvcStackLimit = .;

        /* IRQ stack */
        . = ALIGN(8);
        __IrqStackBase = .;
        /* Place the irq_stack here. */
        KEEP(*(.irq_stack))
        __IrqStackLimit = .;

        /* FIQ stack */
        . = ALIGN(8);
        __FiqStackBase = .;
        /* Place the fiq_stack here. */
        KEEP(*(.fiq_stack))
        __FiqStackLimit = .;

        /* Undefined stack */
        . = ALIGN(8);
        __UndStackBase = .;
        /* Place the und_stack here. */
        KEEP(*(.und_stack))
        __UndStackLimit = .;

        /* Abort stack */
        . = ALIGN(8);
        __AbtStackBase = .;
        /* Place the abt_stack here. */
        KEEP(*(.abt_stack))
        __AbtStackLimit = .;

        /* Thread stack */
        . = ALIGN(8);
        /* Place the thread stack here. */
        KEEP(*(.stack.*))

        /* BSP BSS */
        . = ALIGN(0x04);
        __bss_start__ = .;
        _bss = .;
        ./rzv_gen/*.o (.bss*)
        ./rzv/fsp/*.o (.bss*)
        ./rzv/board/*.o (.bss*)
        *(COMMON)
        . = ALIGN(0x04);
        __bss_end__ = .;
        _ebss = .;
        _end = .;
    } > DTCM
    .sdram_load_section :  ALIGN( 0x04 )
    {
        . = ALIGN ( 0x04 ) ;
        _sdram_load_start = .;
        ./rzv/linaro/*.o(.data*)
        . = ALIGN(0x04);
        _sdram_load_end = .;
    } > DDR_SDRAM_CACHE
    .sram_load_section0 : ALIGN( 0x04 )
    {
        /* User code */
        _sram_load_start = .;
        __text_usr_start = .;
        * (.text .text.*) /* Take all remaining .text section */
        . = ALIGN( 0x04 );
        __text_usr_end = .;
    } > SRAM_CACHE
    .loader_dummy_sram :
    {
        _loader_dummy_sram_start = .;
        KEEP(*(.loader_dummy_sram));
        _loader_dummy_sram_end = .;
    } > DUMMY AT > SRAM_CACHE
    .sram_load_section1 : ALIGN( 0x04 )
    {
        /* user data */
        __data_usr_start = .;
        * (.data .data.*)  /* Take all remaining .data section */

        . = ALIGN(0x04);

        __rodata_usr_start = .;
        * (.rodata .rodata.*) /* Take all remaining .rodata section */

        . = ALIGN(0x04);
        /* All data end */
        __data_usr_end = .;
        _sram_load_end = .;
    } > SRAM_CACHE
    .sram_noload_section (NOLOAD) :
    {
        /* user BSS */
        . = ALIGN( 0x04 );
        __bss_usr_start__ = .;

        * (.bss .bss.*) /* Take all remaining .bss section */

        . = ALIGN(0x04);
        __bss_usr_end__ = .;
        _end_usr = .;

        . = ALIGN(0x10);
        _cbuffer_start = .;
        KEEP(*(.cache_buffer*))
        _cbuffer_end = .;
    } > SRAM_CACHE
    .sram_uncache_section (NOLOAD) :
    {
        . = ALIGN(0x10);
        _ncbuffer_start = .;
        KEEP(*(.noncache_buffer*))
        _ncbuffer_end = .;
    } > SRAM_UNCACHE
    .wait_data  :
    {
        KEEP(*(.wait_data))
    } > INIT_WAIT_AREA
    .wait_data_other_core  :
    {
        KEEP(*(.wait_data_other_core))
    } > INIT_WAIT_AREA_OTHER_CORE

    .sdram_noload_section (NOLOAD) :
    {
        . = ALIGN ( 0x10 ) ;
        PROVIDE(_cbuffer_sdram_start = .);
        PROVIDE(_cbuffer_sdram_end = .);
    } > DDR_SDRAM_CACHE
    .sdram_uncache_section (NOLOAD) :
    {
        . = ALIGN ( 0x10 ) ;
        PROVIDE(_ncbuffer_sdram_start = .);
        *(.mutex_flags);
        PROVIDE(_ncbuffer_sdram_end = .);
    } > DDR_SDRAM_UNCACHE

    __tz_MHU_SHMEM = ABSOLUTE ( MHU_SHMEM_START ) ;
    . = __tz_MHU_SHMEM;
    .resource_table (NOLOAD) :
    {
        PROVIDE(__rsctbl_start = .);
        *  (  .resource_table  )
        PROVIDE(__rsctbl_end = .);
    } > OPENAMP_RSCTBL
    __tz_MHU_SHMEM = ABSOLUTE ( MHU_SHMEM_START ) ;
    . = __tz_MHU_SHMEM;
    .mhu_shmem (NOLOAD) :
    {
        PROVIDE(__mhu_shmem_start = .);
        . += MHU_SHMEM_LENGTH;
        PROVIDE(__mhu_shmem_end = .);
    } > MHU_SHMEM
    __tz_OPENAMP_VRING = ABSOLUTE ( OPENAMP_VRING_START ) ;
    . = __tz_OPENAMP_VRING;
    .vring (NOLOAD) :
    {
        PROVIDE(__vring_start = .);
        . += OPENAMP_VRING_LENGTH;
        PROVIDE(__vring_end = .);
    } > OPENAMP_VRING

    _itcm_load_addr = FLASH_DATA_START;
    _itcm_load_size = _itcm_load_end - _itcm_load_start;
    _itcm_load_start = _itcm_load_start + ITCM_PRV_AXI_START;
    _sram_load_addr = FLASH_DATA_START + _itcm_load_size;
    _sram_load_size = _sram_load_end - _sram_load_start;
    _sdram_load_addr = FLASH_DATA_START + _itcm_load_size + _sram_load_size;
    _sdram_load_size = _sdram_load_end - _sdram_load_start;
    .header : {
        _header_start = .;
        LONG(_itcm_load_addr)
        LONG(_itcm_load_start)
        LONG(_itcm_load_size)
        LONG(0xFFFFFFFF - _itcm_load_addr)
        LONG(0xFFFFFFFF - _itcm_load_start)
        LONG(0xFFFFFFFF - _itcm_load_size)
        LONG(_sram_load_addr)
        LONG(_sram_load_start)
        LONG(_sram_load_size)
        LONG(0xFFFFFFFF - _sram_load_addr)
        LONG(0xFFFFFFFF - _sram_load_start)
        LONG(0xFFFFFFFF - _sram_load_size)
        LONG(_sdram_load_addr)
        LONG(_sdram_load_start)
        LONG(_sdram_load_size)
        LONG(0xFFFFFFFF - _sdram_load_addr)
        LONG(0xFFFFFFFF - _sdram_load_start)
        LONG(0xFFFFFFFF - _sdram_load_size)
        LONG(INIT_WAIT_AREA_START)
        LONG(0x1234FEDC)
        _header_end = .;
    } > HEADER_REGION
    /* Header reserved area (signature, padding) */
    _header_padding_size = HEADER_LENGTH - ((_header_end + 4)- _header_start);
    .header_reserved : {
        LONG(0x562F5A52)
        FILL(0x00)
        . += _header_padding_size;
    } > HEADER_REGION
}
