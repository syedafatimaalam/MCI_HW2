#include "stm32f303xc.h"
#include "usart.h"

void USART1_Init(uint32_t baud) {
    // Enable GPIOA and USART1 clocks
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;

    // Configure PA9 (TX) and PA10 (RX) as Alternate Function
    GPIOA->MODER &= ~((3 << (9 * 2)) | (3 << (10 * 2)));
    GPIOA->MODER |=  ((2 << (9 * 2)) | (2 << (10 * 2)));
    
    // Set AF7 for USART1 on PA9/PA10
    GPIOA->AFR[1] |= (7 << ((9 - 8) * 4)) | (7 << ((10 - 8) * 4));

    // Configure Baud Rate (Assuming 72 MHz PCLK2)
    USART1->BRR = 72000000 / baud;

    // Enable Transmitter, Receiver, and USART
    USART1->CR1 |= USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

void USART1_Write(uint16_t data) {
    while (!(USART1->ISR & USART_ISR_TXE));
    USART1->TDR = data;
}