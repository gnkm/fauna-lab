import { type ChangeEvent, type DragEvent, useId, useState } from "react";

export function Dropzone({
  disabled,
  onFiles,
}: {
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  const takeFiles = (list: FileList | File[] | null) => {
    if (list === null || disabled) {
      return;
    }
    const files = Array.from(list);
    if (files.length === 0) {
      return;
    }
    onFiles(files);
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    takeFiles(event.target.files);
    event.target.value = "";
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    takeFiles(event.dataTransfer.files);
  };

  const onDragOver = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (!disabled) {
      setDragging(true);
    }
  };

  return (
    <label
      className={dragging ? "dropzone dropzone--active" : "dropzone"}
      htmlFor={inputId}
      onDragEnter={onDragOver}
      onDragOver={onDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      data-testid="upload-dropzone"
    >
      <input
        id={inputId}
        className="dropzone__input"
        type="file"
        accept="image/jpeg,image/png,.jpg,.jpeg,.png"
        multiple
        disabled={disabled}
        onChange={onChange}
        data-testid="upload-input"
      />
      <span className="dropzone__button">ファイルを選択</span>
      <p>
        JPEG / PNG
        を複数選べます。ここにドロップしても登録できます。一部が失敗しても他の登録は続きます。1
        回あたり最大 50 件、1 ファイル 10 MiB までです。
      </p>
    </label>
  );
}
