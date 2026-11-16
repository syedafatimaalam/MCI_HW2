#include "stm32f303xc.h"
#include "adc.h"


//for 1000 samples
// #define BUFFER_SIZE 1000

// volatile uint16_t adc_buffer[BUFFER_SIZE];
// volatile uint32_t sampleCount = 0;
// volatile uint32_t captureDone = 0;

//for 10000 samples
#define BUFFER_SIZE 1000

volatile uint16_t adc_buffer[BUFFER_SIZE];
volatile uint32_t sampleCount = 0;
volatile uint32_t captureDone = 0;

// Total number of ADC conversions
volatile uint32_t totalSamples = 0;
// Circular buffer for continuous UART transmission.
// Must be a power of two.
#define UART_BUFFER_SIZE 2048U

volatile uint16_t uartBuffer[UART_BUFFER_SIZE];

// Index of next position to write.
volatile uint32_t uartHead = 0;

// Index of next position to read.
volatile uint32_t uartTail = 0;

// Number of samples dropped when buffer is full.
volatile uint32_t uartDroppedSamples = 0;

void ADC1_Init(void)
{
    // Enable GPIOA clock (GPIOAEN).
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN;

    // Configure PA0 in analog mode (MODER0 = 11).
    GPIOA->MODER |= (3U << GPIO_MODER_MODER0_Pos);

    // Disable pull-up and pull-down on PA0 (PUPDR0 = 00).
    GPIOA->PUPDR &= ~(3U << GPIO_PUPDR_PUPDR0_Pos);

    // Enable ADC1/ADC2 clock (ADC12EN).
    RCC->AHBENR |= RCC_AHBENR_ADC12EN;

    // Select synchronous ADC clock: HCLK / 1 (CKMODE = 01).
    ADC1_2_COMMON->CCR &= ~ADC12_CCR_CKMODE;
    ADC1_2_COMMON->CCR |= ADC12_CCR_CKMODE_0;

    // Enable ADC voltage regulator (ADVREGEN = 01).
    ADC1->CR &= ~ADC_CR_ADVREGEN;
    ADC1->CR |= ADC_CR_ADVREGEN_0;

    // Wait for voltage regulator startup.
    for (volatile uint32_t i = 0; i < 10000; i++)
    {
        __NOP();
    }

    // Select single-ended calibration (ADCALDIF = 0).
    ADC1->CR &= ~ADC_CR_ADCALDIF;

    // Start ADC calibration (ADCAL = 1).
    ADC1->CR |= ADC_CR_ADCAL;

    while (ADC1->CR & ADC_CR_ADCAL) {}

    // Select 12-bit resolution (RES = 00).
    ADC1->CFGR &= ~ADC_CFGR_RES;

    // Disable continuous conversion (CONT = 0).
    ADC1->CFGR &= ~ADC_CFGR_CONT;

    // Select TIM2 TRGO as external trigger (EXTSEL = 1011).
    ADC1->CFGR &= ~ADC_CFGR_EXTSEL;
    ADC1->CFGR |= (11U << ADC_CFGR_EXTSEL_Pos);

    // Trigger on rising edge (EXTEN = 01).
    ADC1->CFGR &= ~ADC_CFGR_EXTEN;
    ADC1->CFGR |= (1U << ADC_CFGR_EXTEN_Pos);

    // Configure one regular conversion (L = 0000).
    ADC1->SQR1 &= ~ADC_SQR1_L;

    // Select ADC1 channel 1, PA0 (SQ1 = 00001).
    ADC1->SQR1 &= ~ADC_SQR1_SQ1;
    ADC1->SQR1 |= (1U << ADC_SQR1_SQ1_Pos);

    // Set channel 1 sampling time (SMP1 = 100).
    ADC1->SMPR1 &= ~ADC_SMPR1_SMP1;
    ADC1->SMPR1 |= (4U << ADC_SMPR1_SMP1_Pos);

    // Clear ADC ready flag (ADRDY).
    ADC1->ISR = ADC_ISR_ADRDY;

    // Enable ADC (ADEN = 1).
    ADC1->CR |= ADC_CR_ADEN;

    while (!(ADC1->ISR & ADC_ISR_ADRDY)) {}

    // Enable end-of-conversion interrupt (EOCIE).
    ADC1->IER |= ADC_IER_EOCIE;

    // Enable ADC1 interrupt in NVIC.
    NVIC_EnableIRQ(ADC1_2_IRQn);

    // Arm ADC to wait for external triggers (ADSTART).
    ADC1->CR |= ADC_CR_ADSTART;
}

//for 1000 samples
// void ADC1_2_IRQHandler(void)
// {
//     if (ADC1->ISR & ADC_ISR_EOC)
//     {
//         // Reading DR retrieves the conversion and clears EOC.
//         uint16_t value = (uint16_t)ADC1->DR;

//         if (sampleCount < BUFFER_SIZE)
//         {
//             adc_buffer[sampleCount] = value;
//             sampleCount++;

//             if (sampleCount == BUFFER_SIZE)
//             {
//                 captureDone = 1;
//             }
//         }
//     }
// }

//for 10000 samples
void ADC1_2_IRQHandler(void)
{
    if (ADC1->ISR & ADC_ISR_EOC)
    {
        // Read the 12-bit ADC result.
        uint16_t value = (uint16_t)ADC1->DR;

        // Count completed ADC conversions.
        totalSamples++;

        // Preserve the first 1000 samples for debugging.
        if (sampleCount < BUFFER_SIZE)
        {
            adc_buffer[sampleCount] = value;
            sampleCount++;

            if (sampleCount == BUFFER_SIZE)
            {
                captureDone = 1;
            }
        }

        // Calculate the next circular-buffer position.
        uint32_t nextHead =
            (uartHead + 1U) & (UART_BUFFER_SIZE - 1U);

        // Store the sample if the buffer is not full.
        if (nextHead != uartTail)
        {
            uartBuffer[uartHead] = value;
            uartHead = nextHead;
        }
        else
        {
            // Record samples lost due to buffer overflow.
            uartDroppedSamples++;
        }
    }
}