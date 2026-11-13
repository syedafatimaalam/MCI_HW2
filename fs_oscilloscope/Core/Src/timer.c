#include "stm32f303xc.h"
#include "timer.h"

void TIMER_Init(void)
{
    // Enable TIM2 clock (TIM2EN).
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;

    // Disable TIM2 while configuring (CEN = 0).
    TIM2->CR1 &= ~TIM_CR1_CEN;

    // Prescaler = 0, so timer clock remains 8 MHz (PSC).
    TIM2->PSC = 0;

    // 800 ticks per update: 8 MHz / 800 = 10 kHz (ARR).
    TIM2->ARR = 799;

    // Select update event as trigger output (MMS = 010).
    TIM2->CR2 &= ~TIM_CR2_MMS;
    TIM2->CR2 |= (2U << TIM_CR2_MMS_Pos);

    // Load prescaler and auto-reload values (UG).
    TIM2->EGR = TIM_EGR_UG;

    // Clear pending update interrupt flag (UIF).
    TIM2->SR &= ~TIM_SR_UIF;

    // Start TIM2 (CEN = 1).
    TIM2->CR1 |= TIM_CR1_CEN;
}