from rezgui.qt import QtCore, QtGui
from rezgui.widgets.PackageSelectWidget import PackageSelectWidget
from rezgui.widgets.VariantCellWidget import VariantCellWidget
from rez.packages import Variant
from functools import partial


class ContextTableWidget(QtGui.QTableWidget):
    default_row_count = 10

    contextModified = QtCore.Signal()
    variantSelected = QtCore.Signal(object)

    def __init__(self, settings=None, read_only=False, parent=None):
        """Create a context table.

        Args:
            settings (`SettingsWidget`): Context settings, such as search path.
                Ignored if `read_only` is True.
            read_only (bool): Read-only mode.
        """
        super(ContextTableWidget, self).__init__(self.default_row_count,
                                                 2, parent)
        self.settings = settings
        self.read_only = read_only
        self.context = None
        self.modified = False
        self.diff_mode = False
        self._current_variant = None

        self.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        hh = self.horizontalHeader()
        hh.setDefaultSectionSize(12 * self.fontMetrics().height())

        vh = self.verticalHeader()
        vh.setResizeMode(QtGui.QHeaderView.ResizeToContents)
        vh.setVisible(False)

        self.currentCellChanged.connect(self._currentCellChanged)

        self.set_context()

    def selectionCommand(self, index, event=None):
        row = index.row()
        column = index.column()

        widget = self.cellWidget(row, column)
        if widget:
            if isinstance(widget, PackageSelectWidget):
                return QtGui.QItemSelectionModel.Clear
        else:
            item = self.item(row, column)
            if not item or not item.text():
                return QtGui.QItemSelectionModel.NoUpdate

        return QtGui.QItemSelectionModel.ClearAndSelect

    def current_variant(self):
        """Returns the currently selected variant, if any."""
        return self._current_variant

    def set_context(self, context=None):
        """Set contents to the given `ResolvedContext`."""
        self.clear()
        self.setHorizontalHeaderLabels(["request", "resolve"])
        self.modified = False
        self.context = None

        if context:
            self._apply_context(context, 0, 1)
            self.context = context
        else:
            self._set_package_cell(0, 0)

    def get_request(self):
        """Get the current request list.

        Returns:
            List of strings.
        """
        return self._get_request(0)

    def refresh(self):
        for column in (0, 1):
            for widget in self._iter_column_widgets(column):
                widget.refresh()

    def _currentCellChanged(self, currentRow, currentColumn,
                            previousRow, previousColumn):
        # clear selection if inactive cell is clicked
        indexes = self.selectedIndexes()
        if indexes:
            index = indexes[0]
            if index.row() != currentRow or index.column() != currentColumn:
                self.clearSelection()

        # detect click on variant cell
        widget = self.cellWidget(currentRow, currentColumn)
        if widget and isinstance(widget, VariantCellWidget):
            self._current_variant = widget.variant
        else:
            self._current_variant = None
            self.setCurrentIndex(QtCore.QModelIndex())
        self.variantSelected.emit(self._current_variant)

    def _iter_column_widgets(self, column):
        for i in range(self.rowCount()):
            widget = self.cellWidget(i, column)
            if widget:
                yield widget
            else:
                break

    def _get_request(self, column):
        request_strs = []
        for edit in self._iter_column_widgets(column):
            txt = str(edit.text()).strip()
            if txt:
                request_strs.append(txt)
        return request_strs

    def _apply_context(self, context, request_column, resolve_column):
        requests = context.requested_packages()
        resolved = context.resolved_packages[:]
        num_requests = len(requests)

        for i, request in enumerate(requests):
            self._set_package_cell(i, request_column, request)
            variant = context.get_resolved_package(request.name)
            if variant:
                self._set_variant_cell(i, resolve_column, variant)
                resolved = [x for x in resolved if x.name != request.name]

        for i, variant in enumerate(resolved):
            self._set_variant_cell(i + num_requests, resolve_column, variant)

        self._set_package_cell(num_requests, request_column)

    def _set_package_cell(self, row, column, request=None):
        if row >= self.rowCount():
            self.setRowCount(row + 1)
        if self.cellWidget(row, column):
            return

        txt = str(request) if request else ""

        edit = PackageSelectWidget(self.settings)
        edit.setText(txt)
        self.setCellWidget(row, column, edit)
        edit.textChanged.connect(partial(self._packageTextChanged, row, column))
        edit.focusOut.connect(partial(self._packageFocusOut, row, column))
        edit.focusOutViaKeyPress.connect(partial(self._packageFocusOutViaKeyPress,
                                                 row, column))
        #edit.refresh()
        return edit

    def _set_variant_cell(self, row, column, variant):
        if row >= self.rowCount():
            self.setRowCount(row + 1)
        widget = VariantCellWidget(variant, self.settings)
        self.setCellWidget(row, column, widget)

    def _set_cell_text(self, row, column, txt):
        if row >= self.rowCount():
            self.setRowCount(row + 1)

        if self.cellWidget(row, column):
            self.removeCellWidget(row, column)
        item = QtGui.QTableWidgetItem(txt)
        self.setItem(row, column, item)

    def _packageTextChanged(self, row, column, txt):
        if txt:
            self._set_package_cell(row + 1, column)

        if not self.modified:
            self.modified = True
            resolve_column = 1 if column == 0 else 2
            self._enable_column(resolve_column, False)
            self.contextModified.emit()

    def _enable_column(self, column, enabled):
        for widget in self._iter_column_widgets(column):
            widget.setEnabled(enabled)

    def _packageFocusOut(self, row, column, txt):
        if txt:
            self._set_package_cell(row + 1, column)
        elif self.cellWidget(row + 1, column):
            self._delete_cell(row, column)

    def _packageFocusOutViaKeyPress(self, row, column, txt):
        if txt:
            self._set_current_cell(row + 1, column)
        elif self.cellWidget(row + 1, column):
            self._delete_cell(row, column)

    def _delete_cell(self, row, column):
        for i in range(row, self.rowCount()):
            edit = self.cellWidget(i, column)
            assert edit and isinstance(edit, PackageSelectWidget)

            next_edit = self.cellWidget(i + 1, column)
            if next_edit:
                next_edit.clone_into(edit)
            else:
                self.removeCellWidget(i, column)
        self._trim_trailing_rows()

    def _trim_trailing_rows(self):
        n = 0
        for i in reversed(range(self.default_row_count, self.rowCount())):
            row_clear = not any(self.cellWidget(i, x)
                                for x in range(self.columnCount()))
            if row_clear:
                n += 1
            else:
                break
        if n:
            row, column = self.currentRow(), self.currentColumn()
            self.setRowCount(self.rowCount() - n)
            self._set_current_cell(row, column)

    def _set_current_cell(self, row, column):
        self.setCurrentCell(row, column)
        edit = self.cellWidget(row, column)
        if edit and hasattr(edit, "setCurrent"):
            edit.setCurrent()