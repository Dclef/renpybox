import type { ReactNode } from 'react';
import { Tabs } from '@mantine/core';

import type { PageKey } from '../nav';
import { PageHeader } from '../ui';

export function GroupPage(props: {
  title: string;
  description: string;
  tabs: { key: PageKey; label: string }[];
  active: PageKey;
  onSelect: (key: PageKey) => void;
  children: ReactNode;
}) {
  const { title, description, tabs, active, onSelect, children } = props;
  return (
    <div className="rb-page rb-group-page">
      <PageHeader title={title} description={description} />
      <Tabs value={active} onChange={(value) => { if (value) onSelect(value as PageKey); }}>
        <Tabs.List>
          {tabs.map((tab) => (
            <Tabs.Tab key={tab.key} value={tab.key}>{tab.label}</Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <div className="rb-group-panel">{children}</div>
    </div>
  );
}
