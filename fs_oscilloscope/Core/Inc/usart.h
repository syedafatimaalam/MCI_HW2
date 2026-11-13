#ifndef USART_H
#define USART_H

#include <stdint.h>

void USART1_Init(uint32_t baud);
void USART1_Write(uint16_t data);

#endif