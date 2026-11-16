#include "stm32f303xc.h"
#include "timer.h"
#include "adc.h"
#include "usart.h"

#define UART_BUFFER_SIZE 2048U
#define PACKET_SAMPLES 100U

extern volatile uint16_t uartBuffer[UART_BUFFER_SIZE];
extern volatile uint32_t uartHead;
extern volatile uint32_t uartTail;
extern volatile uint32_t uartDroppedSamples;

int main(void)
{
    SystemCoreClockUpdate();

    USART1_Init(230400);
    ADC1_Init();
    TIMER_Init();

    uint8_t packetNumber = 0;

    while (1)
    {
        uint32_t available =
            (uartHead - uartTail) & (UART_BUFFER_SIZE - 1U);

        if (available >= PACKET_SAMPLES)
        {
            uint8_t checksum = packetNumber;

            // Packet header.
            USART1_Write(0xFF);
            USART1_Write(0xFF);

            // Packet number.
            USART1_Write(packetNumber);

            // Transmit 100 ADC samples.
            for (uint32_t i = 0; i < PACKET_SAMPLES; i++)
            {
                uint16_t sample = uartBuffer[uartTail];

                uartTail =
                    (uartTail + 1U) & (UART_BUFFER_SIZE - 1U);

                uint8_t low = sample & 0xFFU;
                uint8_t high = (sample >> 8) & 0xFFU;

                USART1_Write(low);
                USART1_Write(high);

                checksum ^= low;
                checksum ^= high;
            }

            // Packet checksum.
            USART1_Write(checksum);

            packetNumber++;
        }
    }
}