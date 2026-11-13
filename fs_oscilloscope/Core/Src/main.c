// #include "stm32f303xc.h"
// #include "timer.h"
// #include "adc.h"

// extern volatile uint16_t adc_buffer[1000];
// extern volatile uint32_t sampleCount;
// extern volatile uint32_t captureDone;

// int main(void)
// {
//     // Use the default 8 MHz HSI system clock.
//     SystemCoreClockUpdate();

//     // Configure ADC before starting the sampling timer.
//     ADC1_Init();

//     // Start TIM2 at 10 kHz.
//     TIMER_Init();

//     // Wait until 1000 samples have been captured.
//     while (captureDone == 0)
//     {
//         __NOP();
//     }

//     // Stop TIM2 after capture (CEN = 0).
//     TIM2->CR1 &= ~TIM_CR1_CEN;

//     // Keep captured samples available for debugging.
//     while (1)
//     {
//         __NOP();
//     }
// }

#include "stm32f303xc.h"
#include "timer.h"
#include "adc.h"

extern volatile uint32_t sampleCount;
extern volatile uint32_t captureDone;
extern volatile uint32_t totalSamples;

// Stores the number of ADC samples counted in one second.
volatile uint32_t samplesInOneSecond = 0;

int main(void)
{
    // Update the clock frequency.
    SystemCoreClockUpdate();

    // Initialize ADC.
    ADC1_Init();

    // Configure SysTick for a 1-second interval.
    // SysTick LOAD is 24-bit, so 8 MHz - 1 fits.
    SysTick->LOAD = 8000000 - 1;

    // Clear current SysTick counter (VAL).
    SysTick->VAL = 0;

    // Use processor clock and enable SysTick (CLKSOURCE, ENABLE).
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk |
                    SysTick_CTRL_ENABLE_Msk;

    // Start 10 kHz ADC sampling.
    TIMER_Init();

    // Wait until one second has elapsed.
    while (!(SysTick->CTRL & SysTick_CTRL_COUNTFLAG_Msk))
    {
        __NOP();
    }

    // Stop TIM2 (CEN = 0).
    TIM2->CR1 &= ~TIM_CR1_CEN;

    // Disable ADC end-of-conversion interrupts (EOCIE = 0).
    ADC1->IER &= ~ADC_IER_EOCIE;

    // Record the number of conversions.
    samplesInOneSecond = totalSamples;

    // Stay here for debugger inspection.
    while (1)
    {
        __NOP();
    }
}