#include "blinky_thread.h"

/* Blinky Thread entry function */
void blinky_thread_entry (__attribute__((unused)) void * pvParameters)
{
    bsp_io_level_t pin_level = BSP_IO_LEVEL_LOW;

    while (1)
    {
        /* Write to monitor LED PB4/LED0 */
        R_BSP_PinWrite((bsp_io_port_pin_t) BSP_IO_PORT_11_PIN_04, pin_level);

        /* Toggle level for next write */
        if (BSP_IO_LEVEL_LOW == pin_level)
        {
            pin_level = BSP_IO_LEVEL_HIGH;
        }
        else
        {
            pin_level = BSP_IO_LEVEL_LOW;
        }

        vTaskDelay(configTICK_RATE_HZ);
    }
}
