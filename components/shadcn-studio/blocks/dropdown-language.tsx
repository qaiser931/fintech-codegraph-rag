'use client'

import { useState } from 'react'
import type { ReactElement } from 'react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'

type Props = {
  trigger: ReactElement
  defaultOpen?: boolean
  align?: 'start' | 'center' | 'end'
}

const LanguageDropdown = ({ defaultOpen, align, trigger }: Props) => {
  const [language, setLanguage] = useState('english')

  return (
    <DropdownMenu defaultOpen={defaultOpen}>
      <DropdownMenuTrigger render={trigger} />
      <DropdownMenuContent className='w-50' align={align || 'end'}>
        <DropdownMenuRadioGroup value={language} onValueChange={setLanguage}>
          <DropdownMenuRadioItem value='english'>English</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value='german'>Deutsch</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value='spanish'>Española</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value='portuguese'>Português</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value='korean'>한국인</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default LanguageDropdown
