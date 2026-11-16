#include "stm32f303xc.h"
#include "usart.h"

void USART1_Init(uint32_t baud)
{
    // Enable GPIOC clock.
    RCC->AHBENR |= RCC_AHBENR_GPIOCEN;

    // Enable USART1 clock.
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;

    // Disable USART1 before configuration.
    USART1->CR1 &= ~USART_CR1_UE;

    // Configure PC4 as Alternate Function mode (MODER4 = 10).
    GPIOC->MODER &= ~(3U << 8);
    GPIOC->MODER |=  (2U << 8);

    // Select AF7 for USART1_TX on PC4.
    GPIOC->AFR[0] &= ~(0xFU << 16);
    GPIOC->AFR[0] |=  (7U << 16);

    // Configure 8-bit data, no parity, oversampling by 16.
    USART1->CR1 &= ~((1U << 12) |
                     (1U << 28) |
                     USART_CR1_PCE |
                     USART_CR1_OVER8);

    // Configure one stop bit (STOP = 00).
    USART1->CR2 &= ~USART_CR2_STOP;

    // Baud rate assuming USART1 clock is 8 MHz.
    USART1->BRR = (8000000U + baud / 2U) / baud;

    // Enable transmitter.
    USART1->CR1 |= USART_CR1_TE;

    // Enable USART1.
    USART1->CR1 |= USART_CR1_UE;
}

void USART1_Write(uint16_t data)
{
    // Wait until transmit register is empty.
    while (!(USART1->ISR & USART_ISR_TXE))
    {
    }

    // Transmit lower 8 bits.
    USART1->TDR = (uint8_t)data;
}