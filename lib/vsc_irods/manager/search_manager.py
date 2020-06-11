import os
import fnmatch
import warnings
import itertools
from irods.column import Criterion
from irods.models import Collection, DataObject
from vsc_irods.manager import Manager


class SearchManager(Manager):
    """ A class for easier searching in the iRODS file system """

    def glob(self, *args, debug=False, **kwargs):
        """ As iglob(), but returns a list instead of an iterator,
        similar to the glob.iglob builtin.
        """
        results = [hit for hit in self.iglob(*args, debug=debug, **kwargs)]

        self.log('DBG| returning %s' % str(results), debug)
        return results

    def iglob(self, pattern, debug=False):
        """ Returns an iterator of iRODS collection and data object paths
        which match the given pattern, similar to the glob.iglob builtin.

        .. note::
 
            Currently only '*' is expanded. The other special characters
            '?' and '[]' are not (yet) taken into account.

        Examples:

        >>> session.glob('m*/ch4.xyz')
            ['molecules_database/ch4.xyz']
        >>> session.glob('./*/*')
            ['./molecule_database/a.out', './foo/bar.so']
        >>> session.glob('~/foo/c*.xyz')
            ['~/foo/ch4.xyz', '~/foo/co2.xyz']

        Arguments:

        pattern: str
            The search pattern

        debug: bool (default: False)
            Set to True for debugging info
        """
        self.log('DBG| glob pattern = %s' % pattern, debug)

        if '*' not in pattern:
            path = self.session.path.get_absolute_irods_path(pattern)

            if (self.session.data_objects.exists(path) or
                self.session.collections.exists(path)):
                yield pattern
            else:
                yield
        else:
            index = pattern.index('*')
            path = os.path.dirname(pattern[:index])
            remainder = pattern[len(path)+1:] if len(path) > 0 else pattern

            self.log('DBG| path = %s' % path, debug)
            self.log('DBG| remainder = %s' % remainder, debug)

            gen = self.find(irods_path=path, pattern=remainder, types='d,f',
                            use_wholename=True, debug=debug)

            for result in gen:
                yield result

    def find(self, irods_path='.', pattern='*', use_wholename=False,
             types='d,f', debug=False):
        """ Returns a list of iRODS collection and data object paths
        which match the given pattern, similar to the UNIX `find` command.

        Examples:

        >>> session.find('.', name='*mol*/c*.xyz', types='f')
            ['data/molecules/c6h6.xyz', './data/molecules/ch3cooh.xyz']
        >>> session.find('~/data', name='molecules', types='d')
            ['~/data/molecules']

        Arguments:

        irods_path: str (default: '.')
            Root of the directory tree in which to search

        pattern: str (default: '*')
            The search pattern

        use_wholename: bool (default: False)
            Whether it is the whole (absolute) path name that has to
            match the pattern, or only the basename of the collection
            or data object.

        types: str (default: 'd,f')
            Comma-separated list of one or more of the following characters
            to select the type of results to include:

            * 'd' for directories (i.e. collections)
            * 'f' for files (i.e. data objects)

		debug: bool (default: False)
            Set to True for debugging info
        """
        def get_final_path(path_abs):
            # Paths returned by find() must start with the given irods_path
            # This function determines this path from the given absolute path,
            # and the irods_path and irods_path_abs variables
            path_final = os.path.join(irods_path,
                                      path_abs[len(irods_path_abs)+1:])
            msg = 'DBG| path_abs = %s ; irods_path_abs = %s ; path_final = %s'
            self.log(msg % (path_abs, irods_path_abs, path_final), debug)
            return path_final

        irods_path_abs = self.session.path.get_absolute_irods_path(irods_path)

        if not use_wholename and '/' in pattern:
            msg = "Pattern %s contains a slash. UNIX file names usually don't, "
            msg += "so this search will probably yield no results. Setting "
            msg += "'wholename=True' may help you find what you're looking for."
            warning.warn(msg % pattern)

        for t in types.split(','):
            if t == 'd':
                coll_name = os.path.join(irods_path_abs, pattern)
                coll_name = coll_name.replace('*', '%')
                self.log('DBG| find pattern coll_name = %s' % coll_name, debug)

                criteria = [Criterion('like', Collection.name, coll_name)]
                fields = [Collection.name]

                q = self.session.query(*fields).filter(*criteria)

                for result in q.get_results():
                    path = result[Collection.name]
                    path = get_final_path(path)
                    yield path

            elif t == 'f':
                obj_name = os.path.basename(pattern).replace('*', '%')
                self.log('DBG| find pattern obj_name = %s' % obj_name, debug)

                # PRC uses Collection.name criteria as follows:
                #   /.../dir -> only files in this collection
                #   /.../dir/% -> only files in all subcollections
                # To cover both, we need two generators.
                dirs = [os.path.dirname(pattern),
                        os.path.join(os.path.dirname(pattern), '*')]

                generators = []
                for d in dirs:
                    coll_name = os.path.join(irods_path_abs, d).rstrip('/')
                    coll_name = coll_name.replace('*', '%')
                    self.log('DBG| find pattern coll_name = %s' % coll_name,
                             debug)

                    criteria = [Criterion('like', Collection.name, coll_name),
                                Criterion('like', DataObject.name, obj_name)]
                    fields = [Collection.name, DataObject.name]

                    q = self.session.query(*fields).filter(*criteria)
                    generators.append(q.get_results())

                for result in itertools.chain(*generators):
                    path = os.path.join(result[Collection.name],
                                        result[DataObject.name])
                    path = get_final_path(path)
                    yield path
