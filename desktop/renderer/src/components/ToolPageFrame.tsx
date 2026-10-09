import type { ReactNode } from 'react';
import { Button } from '@mantine/core';
import { ArrowLeft } from 'lucide-react';

import { useT } from '../i18n';
import { Banner, PageHeader } from '../ui';

export function ToolPageFrame(props: {
  title: string;
  description: string;
  blocked: boolean;
  onBack: () => void;
  onOpenProject: () => void;
  children: ReactNode;
}) {
  const { title, description, blocked, onBack, onOpenProject, children } = props;
  const t = useT();
  return (
    <div className="rb-page rb-tool-page">
      <PageHeader
        title={title}
        description={description}
        actions={<Button variant="default" leftSection={<ArrowLeft size={16} />} onClick={onBack}>{t('app_back_to_toolbox')}</Button>}
      />
      {blocked ? (
        <Banner tone="warning">
          {t('app_tool_needs_project')}
          <Button variant="default" onClick={onOpenProject}>{t('app_go_project_settings')}</Button>
        </Banner>
      ) : (
        <div className="rb-tool-panel">{children}</div>
      )}
    </div>
  );
}
